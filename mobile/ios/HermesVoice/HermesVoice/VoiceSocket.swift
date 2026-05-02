import Foundation
import os

actor VoiceSocket {
    private let config: AppConfig
    private let logger = Logger(subsystem: "com.dashanddata.HermesVoice", category: "voice-socket")
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    private var task: URLSessionWebSocketTask?
    private var continuation: AsyncStream<VoiceSocketEvent>.Continuation?
    private var pendingAudioPrelude: ServerFrame?

    init(config: AppConfig) {
        self.config = config
    }

    func events() -> AsyncStream<VoiceSocketEvent> {
        AsyncStream { continuation in
            self.continuation = continuation
            continuation.onTermination = { [weak self] _ in
                Task {
                    await self?.disconnect(reason: "event stream ended")
                }
            }
        }
    }

    func connect() async {
        guard config.isVoiceFlowAllowed else {
            continuation?.yield(.failed(config.refusalReason ?? "Voice flow is not allowed for this backend."))
            return
        }

        if task != nil {
            return
        }

        var request = URLRequest(url: config.voiceWebSocketURL)
        if let token = config.developerBearerToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let nextTask = URLSession.shared.webSocketTask(with: request)
        task = nextTask
        nextTask.resume()
        logger.info("Voice socket connecting to \(self.config.voiceWebSocketURL.absoluteString, privacy: .public)")

        do {
            try await sendJSON(ClientHelloFrame())
            await receiveLoop()
        } catch {
            let message = error.localizedDescription
            continuation?.yield(.failed(message))
            logger.error("Voice socket failed: \(message, privacy: .public)")
            await disconnect(reason: message)
        }
    }

    func disconnect(reason: String = "disconnected") async {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        pendingAudioPrelude = nil
        continuation?.yield(.disconnected(reason))
    }

    func sendUtterance(samples: [Float]) async throws {
        guard let task else {
            throw VoiceSocketError.notConnected
        }

        let wav = WavEncoder.pcm16Wav(samples: samples)
        try await sendJSON(StartUtteranceFrame())
        try await task.send(.data(wav))
        try await sendJSON(EndOfUtteranceFrame())
        logger.info("Sent WAV utterance: \(wav.count, privacy: .public) bytes")
    }

    func cancelTurn(turnID: String? = nil) async throws {
        try await sendJSON(CancelTurnFrame(turnID: turnID))
        logger.info("Sent cancel_turn for \(turnID ?? "active", privacy: .public)")
    }

    private func receiveLoop() async {
        while let task {
            do {
                let message = try await task.receive()
                switch message {
                case .string(let text):
                    try handleText(text)
                case .data(let data):
                    handleData(data)
                @unknown default:
                    logger.warning("Unknown WebSocket message received")
                }
            } catch {
                continuation?.yield(.failed(error.localizedDescription))
                await disconnect(reason: error.localizedDescription)
                return
            }
        }
    }

    private func handleText(_ text: String) throws {
        let frame = try decoder.decode(ServerFrame.self, from: Data(text.utf8))
        if frame.event == "audio_chunk" {
            pendingAudioPrelude = frame
            continuation?.yield(.frame(frame))
            return
        }

        if frame.event == "session_started" {
            continuation?.yield(.connected(frame))
        } else {
            continuation?.yield(.frame(frame))
        }
    }

    private func handleData(_ data: Data) {
        if let prelude = pendingAudioPrelude {
            pendingAudioPrelude = nil
            continuation?.yield(.audioChunk(data, prelude))
        } else {
            continuation?.yield(.failed("Received binary audio without an audio_chunk prelude."))
        }
    }

    private func sendJSON<T: Encodable>(_ frame: T) async throws {
        guard let task else {
            throw VoiceSocketError.notConnected
        }
        let data = try encoder.encode(frame)
        guard let text = String(data: data, encoding: .utf8) else {
            throw VoiceSocketError.invalidJSON
        }
        try await task.send(.string(text))
    }
}

enum VoiceSocketError: LocalizedError {
    case notConnected
    case invalidJSON

    var errorDescription: String? {
        switch self {
        case .notConnected:
            return "Voice socket is not connected."
        case .invalidJSON:
            return "Could not encode WebSocket frame."
        }
    }
}
