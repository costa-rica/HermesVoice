import Foundation

struct VoiceSessionRecord: Decodable, Identifiable, Equatable {
    let id: String
    let title: String?
    let createdAt: String
    let updatedAt: String
    let lastMessagePreview: String?
    let messageCount: Int
    let conversationID: String
    let hermesConversationID: String?
    let archivedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastMessagePreview = "last_message_preview"
        case messageCount = "message_count"
        case conversationID = "conversation_id"
        case hermesConversationID = "hermes_conversation_id"
        case archivedAt = "archived_at"
    }

    var displayTitle: String {
        if let title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return title
        }
        if let preview = lastMessagePreview, !preview.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return preview
        }
        return "New conversation"
    }
}

struct VoiceMessageRecord: Decodable, Identifiable, Equatable {
    let id: String
    let sessionID: String
    let turnID: String?
    let role: String
    let text: String
    let final: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case sessionID = "session_id"
        case turnID = "turn_id"
        case role
        case text
        case final
        case createdAt = "created_at"
    }
}

struct VoiceSessionListResponse: Decodable {
    let sessions: [VoiceSessionRecord]
}

struct VoiceSessionResponse: Decodable {
    let session: VoiceSessionRecord
}

struct VoiceMessagesResponse: Decodable {
    let messages: [VoiceMessageRecord]
}

private struct VoiceSessionCreateBody: Encodable {
    let title: String?
}

struct VoiceSessionClient {
    let config: AppConfig
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(config: AppConfig, session: URLSession = .shared) {
        self.config = config
        self.session = session
    }

    func listSessions() async throws -> [VoiceSessionRecord] {
        var request = URLRequest(url: voiceURL("sessions"))
        request.httpMethod = "GET"
        let response: VoiceSessionListResponse = try await send(request)
        return response.sessions
    }

    func createSession(title: String? = nil) async throws -> VoiceSessionRecord {
        var request = URLRequest(url: voiceURL("sessions"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(VoiceSessionCreateBody(title: title))
        let response: VoiceSessionResponse = try await send(request)
        return response.session
    }

    func loadMessages(sessionID: String) async throws -> [VoiceMessageRecord] {
        var request = URLRequest(url: voiceURL("sessions").appending(path: sessionID).appending(path: "messages"))
        request.httpMethod = "GET"
        let response: VoiceMessagesResponse = try await send(request)
        return response.messages
    }

    func archiveSession(sessionID: String) async throws {
        var request = URLRequest(url: voiceURL("sessions").appending(path: sessionID))
        request.httpMethod = "DELETE"
        let _: EmptyVoiceResponse = try await send(request)
    }

    private func voiceURL(_ path: String) -> URL {
        config.baseURL.appending(path: "api").appending(path: "voice").appending(path: path)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthClientError.invalidResponse
        }

        if (200 ..< 300).contains(httpResponse.statusCode) {
            if T.self == EmptyVoiceResponse.self {
                return EmptyVoiceResponse() as! T
            }
            return try decoder.decode(T.self, from: data)
        }

        if let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data) {
            throw AuthClientError.api(envelope.error.message ?? envelope.error.code ?? "Request failed.")
        }
        throw AuthClientError.api(HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
    }
}

private struct EmptyVoiceResponse: Decodable {}
