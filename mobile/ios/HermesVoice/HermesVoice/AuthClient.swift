import Foundation
import Security

struct LoginResponse: Decodable, Equatable {
    let challengeID: String
    let mockCode: String?

    enum CodingKeys: String, CodingKey {
        case challengeID = "challenge_id"
        case mockCode = "mock_code"
    }
}

struct SessionResponse: Decodable, Equatable {
    let authenticated: Bool
}

struct APIErrorEnvelope: Decodable, Equatable {
    let error: APIErrorBody
}

struct APIErrorBody: Decodable, Equatable {
    let code: String?
    let message: String?
    let status: Int?
    let details: String?
}

enum AuthClientError: LocalizedError, Equatable {
    case backendNotAllowed(String)
    case invalidResponse
    case api(String)

    var errorDescription: String? {
        switch self {
        case .backendNotAllowed(let reason):
            return reason
        case .invalidResponse:
            return "The server returned an unexpected response."
        case .api(let message):
            return message
        }
    }
}

struct AuthClient {
    let config: AppConfig
    private let session: URLSession
    private let cookieStore: SessionCookieStore
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(
        config: AppConfig,
        session: URLSession = .shared,
        cookieStore: SessionCookieStore = SessionCookieStore()
    ) {
        self.config = config
        self.session = session
        self.cookieStore = cookieStore
    }

    func restoreSessionCookie() {
        cookieStore.restoreCookie(for: config.baseURL)
    }

    func checkSession() async throws -> Bool {
        restoreSessionCookie()
        var request = URLRequest(url: authURL("session"))
        request.httpMethod = "GET"
        let response: SessionResponse = try await send(request)
        if response.authenticated {
            cookieStore.persistCookie(for: config.baseURL)
        }
        return response.authenticated
    }

    func login(email: String, password: String) async throws -> LoginResponse {
        guard config.isVoiceFlowAllowed else {
            throw AuthClientError.backendNotAllowed(config.refusalReason ?? "Voice flow is not allowed for this backend.")
        }

        var request = URLRequest(url: authURL("login"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode([
            "email": email,
            "password": password,
        ])
        return try await send(request)
    }

    func verify(challengeID: String, code: String) async throws {
        var request = URLRequest(url: authURL("verify"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode([
            "challenge_id": challengeID,
            "code": code,
        ])

        let _: EmptyResponse = try await send(request)
        cookieStore.persistCookie(for: config.baseURL)
    }

    func logout() async throws {
        var request = URLRequest(url: authURL("logout"))
        request.httpMethod = "POST"
        let _: EmptyResponse = try await send(request)
        cookieStore.clearCookie(for: config.baseURL)
    }

    private func authURL(_ path: String) -> URL {
        config.baseURL.appending(path: "api").appending(path: "auth").appending(path: path)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthClientError.invalidResponse
        }

        if (200 ..< 300).contains(httpResponse.statusCode) {
            if T.self == EmptyResponse.self {
                return EmptyResponse() as! T
            }
            return try decoder.decode(T.self, from: data)
        }

        if let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data) {
            throw AuthClientError.api(envelope.error.message ?? envelope.error.code ?? "Request failed.")
        }
        throw AuthClientError.api(HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
    }
}

private struct EmptyResponse: Decodable {}

struct SessionCookieStore {
    private let cookieName = "hv_session"
    private let keychainService = "com.dashanddata.HermesVoice.auth"
    private let keychainAccount = "hv_session_cookie"

    func persistCookie(for baseURL: URL) {
        guard let cookie = sessionCookie(for: baseURL),
              let record = StoredCookie(cookie: cookie),
              let data = try? JSONEncoder().encode(record)
        else {
            return
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)

        var attributes = query
        attributes[kSecValueData as String] = data
        SecItemAdd(attributes as CFDictionary, nil)
    }

    func restoreCookie(for baseURL: URL) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess,
              let data = item as? Data,
              let record = try? JSONDecoder().decode(StoredCookie.self, from: data),
              let cookie = record.cookie,
              cookie.matches(baseURL)
        else {
            return
        }

        HTTPCookieStorage.shared.setCookie(cookie)
    }

    func clearCookie(for baseURL: URL) {
        if let cookie = sessionCookie(for: baseURL) {
            HTTPCookieStorage.shared.deleteCookie(cookie)
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
    }

    private func sessionCookie(for baseURL: URL) -> HTTPCookie? {
        guard let host = baseURL.host else { return nil }
        return HTTPCookieStorage.shared.cookies?.first { cookie in
            cookie.name == cookieName && cookie.domainMatches(host)
        }
    }
}

private struct StoredCookie: Codable {
    let name: String
    let value: String
    let domain: String
    let path: String
    let expiresDate: Date?
    let isSecure: Bool

    init?(cookie: HTTPCookie) {
        name = cookie.name
        value = cookie.value
        domain = cookie.domain
        path = cookie.path
        expiresDate = cookie.expiresDate
        isSecure = cookie.isSecure
    }

    var cookie: HTTPCookie? {
        var properties: [HTTPCookiePropertyKey: Any] = [
            .name: name,
            .value: value,
            .domain: domain,
            .path: path,
        ]
        if let expiresDate {
            properties[.expires] = expiresDate
        }
        if isSecure {
            properties[.secure] = "TRUE"
        }
        return HTTPCookie(properties: properties)
    }
}

private extension HTTPCookie {
    func domainMatches(_ host: String) -> Bool {
        let normalizedDomain = domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
        let normalizedHost = host.lowercased()
        return normalizedHost == normalizedDomain || normalizedHost.hasSuffix(".\(normalizedDomain)")
    }

    func matches(_ baseURL: URL) -> Bool {
        guard let host = baseURL.host else { return false }
        return name == "hv_session" && domainMatches(host)
    }
}

