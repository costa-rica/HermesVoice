import Foundation

enum ActiveState: String, Codable {
    case idle
    case listening
    case thinking
    case thinkingProgress = "thinking_progress"
    case speaking
    case awaitingApproval = "awaiting_approval"
}
