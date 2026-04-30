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

    let socket: VoiceSocket

    init(appConfig: AppConfig) {
        socket = VoiceSocket()
        wireSocket()
    }

    // MARK: - Connection lifecycle

    func connect(config: AppConfig) {
        socket.connect(to: config.webSocketURL)
    }

    func disconnect() {
        socket.disconnect()
    }

    // MARK: - Private: wire socket events into published state

    private func wireSocket() {
        socket.onSessionStarted = { [weak self] _ in
            self?.serverError = nil
        }

        socket.onTurnStarted = { [weak self] f in
            guard let self else { return }
            // Placeholder user message; the transcript frame fills it in
            let msg = ConversationMessage(id: UUID(), role: .user, text: "…", turnID: f.turnID)
            self.messages.append(msg)
        }

        socket.onTranscript = { [weak self] f in
            guard let self else { return }
            // Update the last user message with the real transcript
            if let idx = self.messages.indices.last,
               self.messages[idx].role == .user,
               self.messages[idx].turnID == f.turnID {
                self.messages[idx].text = f.text
            } else {
                let msg = ConversationMessage(id: UUID(), role: .user, text: f.text, turnID: f.turnID)
                self.messages.append(msg)
            }
        }

        socket.onAssistantText = { [weak self] f in
            guard let self else { return }
            // Accumulate into the current assistant bubble for this turn
            if let idx = self.messages.indices.last,
               self.messages[idx].role == .assistant,
               self.messages[idx].turnID == f.turnID {
                self.messages[idx].text = f.text
            } else {
                let msg = ConversationMessage(id: UUID(), role: .assistant, text: f.text, turnID: f.turnID)
                self.messages.append(msg)
            }
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
            log.warning("server error surfaced to UI: \(f.error.code)")
        }
    }
}
