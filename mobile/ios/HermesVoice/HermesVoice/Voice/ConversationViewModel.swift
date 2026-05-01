import Foundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "ConversationViewModel")

// Reconnect backoff: 1 s, 2 s, 4 s, 8 s, 16 s, then cap at 30 s.
private let kBackoffBase: TimeInterval = 1
private let kBackoffMax:  TimeInterval = 30

struct ConversationMessage: Identifiable, Sendable {
    enum Role: Sendable { case user, assistant }
    let id: UUID
    let role: Role
    var text: String
    let turnID: String?
}

@MainActor
final class ConversationViewModel: ObservableObject {

    @Published private(set) var messages: [ConversationMessage] = []
    @Published private(set) var activeState: ActiveState = .idle
    /// Non-nil when the server sends a typed error frame.
    @Published private(set) var serverError: ServerError?

    struct ServerError: Equatable {
        let code: String
        let message: String
    }
    @Published private(set) var isCapturing = false
    @Published private(set) var micPermissionDenied = false
    /// Set to true when the server rejects the session cookie. The view layer
    /// should sign the user out and route back to LoginView.
    @Published private(set) var authExpired = false

    /// True while hands-free (VAD) mode is active.
    @Published private(set) var isHandsFree = false

    let socket: VoiceSocket
    private let capture = AudioCapture()
    private let player = AudioPlayback()
    private let handsFreeCapture = HandsFreeCapture()
    private let vad = VoiceActivityDetector()

    private var appConfig: AppConfig?
    private var reconnectTask: Task<Void, Never>?
    private var backoffDelay: TimeInterval = kBackoffBase

    init(appConfig: AppConfig) {
        socket = VoiceSocket()
        wireSocket()
    }

    // MARK: - Connection lifecycle

    func connect(config: AppConfig) {
        appConfig = config
        backoffDelay = kBackoffBase
        socket.connect(to: config.webSocketURL)
    }

    func disconnect() {
        reconnectTask?.cancel()
        reconnectTask = nil
        stopHandsFree()
        stopCaptureIfNeeded()
        socket.disconnect()
    }

    /// Manually retry the connection (called from the banner tap).
    func reconnect() {
        guard let config = appConfig else { return }
        reconnectTask?.cancel()
        reconnectTask = nil
        backoffDelay = kBackoffBase
        socket.connect(to: config.webSocketURL)
    }

    // MARK: - Private: auto-reconnect

    private func scheduleReconnect() {
        guard let config = appConfig else { return }
        let delay = backoffDelay
        backoffDelay = min(backoffDelay * 2, kBackoffMax)
        log.info("Reconnecting in \(delay, privacy: .public) s")
        reconnectTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            socket.connect(to: config.webSocketURL)
        }
    }

    // MARK: - PTT

    /// Explicitly cancels the current assistant turn — stops playback,
    /// notifies the server, and clears active state.
    func cancelTurn() async {
        let turnID = socket.activeTurnID
        player.cancelCurrentTurn()
        activeState = .idle
        try? await socket.sendCancelTurn(turnID: turnID)
        log.info("cancel_turn sent for turn_id=\(turnID ?? "<nil>")")
    }

    func startPTT() async {
        guard !isCapturing else { return }
        guard socket.connectionState == .connected else { return }

        // Stop any in-progress assistant audio and cancel the server turn.
        await cancelTurn()

        let allowed = await AudioSessionManager.requestMicPermission()
        guard allowed else {
            micPermissionDenied = true
            return
        }
        micPermissionDenied = false

        do {
            try AudioSessionManager.configureForVoice()
            try capture.startCapture()
        } catch {
            serverError = ServerError(code: "AUDIO_ERROR", message: error.localizedDescription)
            return
        }

        do {
            try await socket.sendStartUtterance(format: "wav", sampleRate: 16000)
        } catch {
            capture.stopCapture()  // discard anything captured before send failed
            return
        }

        isCapturing = true
        activeState = .listening
        log.info("PTT started")
    }

    func stopPTT() async {
        guard isCapturing else { return }
        isCapturing = false
        activeState = .idle

        guard let wavData = capture.stopCapture(), wavData.count > 44 else {
            // Nothing real recorded (just the WAV header); tell the server anyway
            try? await socket.sendEndOfUtterance()
            return
        }

        log.info("PTT stopped — sending \(wavData.count) bytes + end_of_utterance")
        do {
            try await socket.sendAudioData(wavData)
            try await socket.sendEndOfUtterance()
        } catch {
            log.error("Failed to send audio: \(error)")
        }
    }

    // MARK: - Hands-free mode

    func startHandsFree() async {
        guard !isHandsFree else { return }
        guard socket.connectionState == .connected else { return }

        let allowed = await AudioSessionManager.requestMicPermission()
        guard allowed else { micPermissionDenied = true; return }
        micPermissionDenied = false

        do {
            try AudioSessionManager.configureForVoice()
            try handsFreeCapture.start()
        } catch {
            serverError = ServerError(code: "AUDIO_ERROR", message: error.localizedDescription)
            return
        }

        wireVAD()
        isHandsFree = true
        log.info("Hands-free mode started")
    }

    func stopHandsFree() {
        guard isHandsFree else { return }
        isHandsFree = false
        vad.reset()
        handsFreeCapture.stop()
        if isCapturing {
            isCapturing = false
            activeState = .idle
        }
        log.info("Hands-free mode stopped")
    }

    /// Force-starts an utterance in hands-free mode (user tapped the speak button).
    func forceStartUtterance() async {
        guard isHandsFree, !isCapturing else { return }
        guard socket.connectionState == .connected else { return }
        await cancelTurn()
        await beginHandsFreeUtterance()
    }

    // Called from View when the app moves to background.
    func handleBackground() async {
        if isHandsFree {
            // Keep hands-free running in background — do nothing.
            return
        }
        if isCapturing { await stopPTT() }
        AudioSessionManager.deactivate()
    }

    // MARK: - Private: hands-free helpers

    private func wireVAD() {
        handsFreeCapture.onAudioLevel = { [weak self] level in
            guard let self else { return }
            self.vad.process(level: level)
        }

        vad.onSpeechStarted = { [weak self] in
            guard let self, self.isHandsFree, !self.isCapturing else { return }
            guard self.activeState == .idle else { return }
            Task { await self.beginHandsFreeUtterance() }
        }

        vad.onSpeechEnded = { [weak self] in
            guard let self, self.isCapturing else { return }
            Task { await self.endHandsFreeUtterance() }
        }
    }

    private func beginHandsFreeUtterance() async {
        guard socket.connectionState == .connected else { return }
        do {
            try await socket.sendStartUtterance(format: "wav", sampleRate: 16000)
        } catch { return }
        handsFreeCapture.beginUtterance()
        isCapturing = true
        activeState = .listening
        log.info("Hands-free utterance begun")
    }

    private func endHandsFreeUtterance() async {
        guard isCapturing else { return }
        isCapturing = false
        activeState = .idle

        guard let wavData = handsFreeCapture.endUtterance(), wavData.count > 44 else {
            try? await socket.sendEndOfUtterance()
            return
        }

        log.info("Hands-free utterance ended — sending \(wavData.count) bytes")
        do {
            try await socket.sendAudioData(wavData)
            try await socket.sendEndOfUtterance()
        } catch {
            log.error("Failed to send hands-free audio: \(error)")
        }
    }

    // MARK: - Private: wire socket events into published state

    private func wireSocket() {
        socket.onConnectionStateChanged = { [weak self] state in
            guard let self else { return }
            switch state {
            case .connected:
                self.backoffDelay = kBackoffBase   // reset on success
            case .failed:
                self.stopCaptureIfNeeded()
                self.scheduleReconnect()
            case .authFailed:
                self.stopCaptureIfNeeded()
                self.authExpired = true
            default:
                break
            }
        }

        socket.onSessionStarted = { [weak self] f in
            guard let self else { return }
            self.serverError = nil  // clear any prior error on fresh session
            self.player.configure(sampleRate: Double(f.downlinkSampleRate))
        }

        socket.onTurnStarted = { [weak self] f in
            guard let self else { return }
            let msg = ConversationMessage(id: UUID(), role: .user, text: "…", turnID: f.turnID)
            self.messages.append(msg)
        }

        socket.onTranscript = { [weak self] f in
            guard let self else { return }
            if let idx = self.messages.indices.last,
               self.messages[idx].role == .user,
               self.messages[idx].turnID == f.turnID {
                self.messages[idx].text = f.text
            } else {
                self.messages.append(
                    ConversationMessage(id: UUID(), role: .user, text: f.text, turnID: f.turnID)
                )
            }
        }

        socket.onAssistantText = { [weak self] f in
            guard let self else { return }
            if let idx = self.messages.indices.last,
               self.messages[idx].role == .assistant,
               self.messages[idx].turnID == f.turnID {
                self.messages[idx].text = f.text
            } else {
                self.messages.append(
                    ConversationMessage(id: UUID(), role: .assistant, text: f.text, turnID: f.turnID)
                )
            }
        }

        socket.onAudioChunk = { [weak self] f, data in
            self?.player.scheduleChunk(data, turnID: f.turnID)
        }

        socket.onActiveState = { [weak self] f in
            self?.activeState = f.state
        }

        socket.onTurnEnd = { [weak self] _ in
            self?.activeState = .idle
        }

        socket.onVoiceTurnSkipped = { [weak self] _ in
            self?.activeState = .idle
        }

        socket.onServerError = { [weak self] f in
            self?.serverError = ServerError(code: f.error.code, message: f.error.message)
            log.warning("server error: \(f.error.code)")
        }
    }

    private func stopCaptureIfNeeded() {
        guard isCapturing else { return }
        isCapturing = false
        activeState = .idle
        if isHandsFree {
            _ = handsFreeCapture.endUtterance()
        } else {
            capture.stopCapture()
        }
    }
}
