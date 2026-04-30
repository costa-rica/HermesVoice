import Foundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "VoiceSocket")

// Accepted downlink formats offered during client_hello, in preference order.
// The server picks the first it supports; V1 ships without Opus.
private let kAcceptedDownlinks = ["aac_adts", "wav_pcm16"]

// Heartbeat interval. The server closes idle connections after its idle timeout
// (default 120 s); pinging at 25 s keeps the connection alive with headroom.
private let kHeartbeatInterval: TimeInterval = 25

@MainActor
final class VoiceSocket: ObservableObject {

    // MARK: - Connection state

    enum ConnectionState: Equatable {
        case disconnected
        case connecting
        case connected
        case authFailed
        case failed
    }

    @Published private(set) var connectionState: ConnectionState = .disconnected

    // Negotiated session info, set on session_started
    @Published private(set) var conversationID: String?
    @Published private(set) var negotiatedFormat: DownlinkFormat?
    @Published private(set) var negotiatedSampleRate: Int?

    // Current active turn ID; nil between turns and after cancel
    @Published private(set) var activeTurnID: String?

    // MARK: - Event callbacks (set by ConversationViewModel)

    var onSessionStarted: ((SessionStartedFrame) -> Void)?
    var onTurnStarted: ((TurnStartedFrame) -> Void)?
    var onTranscript: ((TranscriptFrame) -> Void)?
    var onAssistantText: ((AssistantTextFrame) -> Void)?
    var onActiveState: ((ActiveStateFrame) -> Void)?
    /// Delivers validated (prelude, audio-bytes) pairs; stale and unbound frames are dropped.
    var onAudioChunk: ((AudioChunkFrame, Data) -> Void)?
    var onTurnEnd: ((TurnEndFrame) -> Void)?
    var onVoiceTurnSkipped: ((VoiceTurnSkippedFrame) -> Void)?
    var onServerError: ((ServerErrorFrame) -> Void)?

    // MARK: - Option A audio-chunk binding state

    // One-slot state: the JSON prelude that must immediately precede the next binary frame.
    // A binary arriving with no prelude slot is a protocol violation and is dropped.
    // A prelude whose turn_id doesn't match activeTurnID is stale and is dropped with its binary.
    private(set) var pendingAudioChunk: AudioChunkFrame?

    // MARK: - Private

    private var webSocketTask: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var heartbeatTask: Task<Void, Never>?
    private let urlSession: URLSession

    init(urlSession: URLSession = .shared) {
        self.urlSession = urlSession
    }

    // MARK: - Connect / disconnect

    func connect(to url: URL) {
        disconnect()
        connectionState = .connecting
        let task = urlSession.webSocketTask(with: url)
        webSocketTask = task
        task.resume()
        receiveTask = Task { [weak self] in await self?.runReceiveLoop() }
        heartbeatTask = Task { [weak self] in await self?.runHeartbeat() }
    }

    func disconnect() {
        heartbeatTask?.cancel()
        heartbeatTask = nil
        receiveTask?.cancel()
        receiveTask = nil
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        connectionState = .disconnected
        pendingAudioChunk = nil
        activeTurnID = nil
        conversationID = nil
        negotiatedFormat = nil
        negotiatedSampleRate = nil
    }

    // MARK: - Outbound sends

    func sendStartUtterance(format: String, sampleRate: Int) async throws {
        try await sendEncodable(StartUtteranceFrame(format: format, sampleRate: sampleRate))
    }

    func sendAudioData(_ data: Data) async throws {
        try await webSocketTask?.send(.data(data))
    }

    func sendEndOfUtterance() async throws {
        try await sendEncodable(EndOfUtteranceFrame())
    }

    /// Sends cancel_turn and immediately clears local turn state so stale audio is never delivered.
    func sendCancelTurn(turnID: String? = nil) async throws {
        activeTurnID = nil
        pendingAudioChunk = nil
        try await sendEncodable(CancelTurnOutbound(turnID: turnID))
        log.debug("cancel_turn sent, turn_id=\(turnID ?? "<nil>")")
    }

    // MARK: - Internal frame processing (internal so tests can call directly without networking)

    func processInboundText(_ text: String) {
        let frame = InboundFrame.decode(from: text)
        dispatchInbound(frame, rawText: text)
    }

    func processInboundBinary(_ data: Data) {
        guard let prelude = pendingAudioChunk else {
            log.warning("binary frame received without preceding audio_chunk prelude — dropped")
            return
        }
        pendingAudioChunk = nil

        guard prelude.turnID == activeTurnID else {
            log.debug("stale audio_chunk (turn_id=\(prelude.turnID)) dropped — active=\(self.activeTurnID ?? "<nil>")")
            return
        }

        onAudioChunk?(prelude, data)
    }

    // MARK: - Private: networking loops

    private func runReceiveLoop() async {
        do {
            try await sendEncodable(ClientHelloFrame(acceptedDownlinkFormats: kAcceptedDownlinks))
        } catch {
            log.error("client_hello send failed: \(error)")
            connectionState = .failed
            return
        }

        guard let task = webSocketTask else { return }
        while !Task.isCancelled {
            do {
                let message = try await task.receive()
                switch message {
                case .string(let text):   processInboundText(text)
                case .data(let data):     processInboundBinary(data)
                @unknown default:         break
                }
            } catch {
                if !Task.isCancelled {
                    log.error("WebSocket receive error: \(error)")
                    connectionState = .failed
                }
                return
            }
        }
    }

    private func runHeartbeat() async {
        while !Task.isCancelled {
            do {
                try await Task.sleep(nanoseconds: UInt64(kHeartbeatInterval * 1_000_000_000))
            } catch { return }
            guard connectionState == .connected else { continue }
            try? await sendEncodable(PingOutbound(id: nil))
        }
    }

    // MARK: - Private: frame dispatch

    private func dispatchInbound(_ frame: InboundFrame, rawText: String) {
        switch frame {
        case .sessionStarted(let f):
            conversationID = f.conversationID
            negotiatedFormat = f.downlinkFormat
            negotiatedSampleRate = f.downlinkSampleRate
            connectionState = .connected
            log.info("session_started: id=\(f.conversationID) fmt=\(f.downlinkFormat.rawValue)")
            onSessionStarted?(f)

        case .turnStarted(let f):
            activeTurnID = f.turnID
            log.debug("turn_started: turn_id=\(f.turnID)")
            onTurnStarted?(f)

        case .transcript(let f):
            onTranscript?(f)

        case .assistantText(let f):
            onAssistantText?(f)

        case .activeState(let f):
            onActiveState?(f)

        case .audioChunk(let f):
            // Store the prelude; the binary frame must arrive next.
            pendingAudioChunk = f

        case .turnCompleted:
            break   // turn_end immediately follows; we act on that

        case .turnEnd(let f):
            activeTurnID = nil
            pendingAudioChunk = nil
            log.debug("turn_end: turn_id=\(f.turnID ?? "<nil>")")
            onTurnEnd?(f)

        case .voiceTurnSkipped(let f):
            activeTurnID = nil
            onVoiceTurnSkipped?(f)

        case .pong:
            break   // heartbeat ack, nothing to do

        case .error(let f):
            log.warning("server error: code=\(f.error.code) msg=\(f.error.message)")
            if f.error.code == "AUTH_FAILED" { connectionState = .authFailed }
            onServerError?(f)

        case .unknown(let raw):
            log.debug("unknown frame (ignored): \(raw.prefix(120))")
        }
    }

    // MARK: - Private: send helper

    private func sendEncodable<T: Encodable>(_ value: T) async throws {
        let data = try JSONEncoder().encode(value)
        let text = String(data: data, encoding: .utf8)!
        try await webSocketTask?.send(.string(text))
    }
}
