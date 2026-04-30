import Foundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "ConversationViewModel")

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
    @Published private(set) var connectionState: VoiceSocket.ConnectionState = .disconnected
    @Published private(set) var serverError: String?
    @Published private(set) var isCapturing = false
    @Published private(set) var micPermissionDenied = false

    let socket: VoiceSocket
    private let capture = AudioCapture()
    private let player = AudioPlayback()

    init(appConfig: AppConfig) {
        socket = VoiceSocket()
        wireSocket()
    }

    // MARK: - Connection lifecycle

    func connect(config: AppConfig) {
        socket.connect(to: config.webSocketURL)
    }

    func disconnect() {
        stopCaptureIfNeeded()
        socket.disconnect()
    }

    // MARK: - PTT

    func startPTT() async {
        guard !isCapturing else { return }
        guard socket.connectionState == .connected else { return }

        // Stop any in-progress assistant audio before capturing user speech.
        player.cancelCurrentTurn()

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
            serverError = error.localizedDescription
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

    // Called from View when the app moves to background.
    func handleBackground() async {
        if isCapturing {
            await stopPTT()
        }
        AudioSessionManager.deactivate()
    }

    // MARK: - Private: wire socket events into published state

    private func wireSocket() {
        socket.onSessionStarted = { [weak self] f in
            guard let self else { return }
            self.serverError = nil
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
            self?.serverError = "\(f.error.code): \(f.error.message)"
            log.warning("server error: \(f.error.code)")
        }
    }

    private func stopCaptureIfNeeded() {
        guard isCapturing else { return }
        isCapturing = false
        activeState = .idle
        capture.stopCapture()
    }
}
