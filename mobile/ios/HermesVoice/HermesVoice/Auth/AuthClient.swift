import Foundation

// Error codes mirror the backend's JSON error.code field.
enum AuthError: LocalizedError {
    case invalidCredentials
    case invalidCode
    case emailSendFailed
    case rateLimited(retryAfter: Double?)
    case networkError(Error)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .invalidCredentials:       return "Incorrect email or password."
        case .invalidCode:              return "Invalid or expired code. Try again."
        case .emailSendFailed:          return "Unable to send verification code. Try again later."
        case .rateLimited:              return "Too many attempts. Please wait and try again."
        case .networkError(let e):      return e.localizedDescription
        case .unexpectedResponse(let s): return "Unexpected server response (\(s))."
        }
    }
}

struct AuthClient {
    let baseURL: URL
    private let session: URLSession

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    // Returns the challenge_id to pass to verify().
    func login(email: String, password: String) async throws -> String {
        var req = request(path: "/api/auth/login", method: "POST")
        req.httpBody = try JSONEncoder().encode(["email": email, "password": password])
        let (data, http) = try await perform(req)
        switch http.statusCode {
        case 200:
            let body = try decode([String: String].self, from: data)
            guard let challengeID = body["challenge_id"] else {
                throw AuthError.unexpectedResponse(200)
            }
            return challengeID
        case 401: throw AuthError.invalidCredentials
        case 429: throw AuthError.rateLimited(retryAfter: retryAfter(from: data))
        case 502: throw AuthError.emailSendFailed
        default:  throw AuthError.unexpectedResponse(http.statusCode)
        }
    }

    // Submits the emailed code; on success the server sets the hv_session cookie.
    func verify(challengeID: String, code: String) async throws {
        var req = request(path: "/api/auth/verify", method: "POST")
        req.httpBody = try JSONEncoder().encode(["challenge_id": challengeID, "code": code])
        let (data, http) = try await perform(req)
        switch http.statusCode {
        case 200: return
        case 401: throw AuthError.invalidCode
        case 429: throw AuthError.rateLimited(retryAfter: retryAfter(from: data))
        default:  throw AuthError.unexpectedResponse(http.statusCode)
        }
    }

    // Returns true if the stored hv_session cookie is still valid server-side.
    func checkSession() async throws -> Bool {
        let req = request(path: "/api/auth/session", method: "GET")
        let (data, http) = try await perform(req)
        guard http.statusCode == 200 else { throw AuthError.unexpectedResponse(http.statusCode) }
        let body = try decode([String: Bool].self, from: data)
        return body["authenticated"] ?? false
    }

    func logout() async throws {
        let req = request(path: "/api/auth/logout", method: "POST")
        let (_, http) = try await perform(req)
        guard http.statusCode == 200 else { throw AuthError.unexpectedResponse(http.statusCode) }
    }

    // MARK: - Private helpers

    private func request(path: String, method: String) -> URLRequest {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        components.path = path
        components.query = nil
        var req = URLRequest(url: components.url!)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return req
    }

    private func perform(_ req: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, response) = try await session.data(for: req)
            return (data, response as! HTTPURLResponse)
        } catch {
            throw AuthError.networkError(error)
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        try JSONDecoder().decode(type, from: data)
    }

    private func retryAfter(from data: Data) -> Double? {
        guard let body = try? decode(BackendErrorEnvelope.self, from: data),
              let details = body.error.details else { return nil }
        // Backend format: "Retry after N seconds"
        let parts = details.split(separator: " ")
        if parts.count >= 3, let secs = Double(parts[2]) { return secs }
        return nil
    }
}

private struct BackendErrorEnvelope: Decodable {
    struct Inner: Decodable {
        let code: String
        let message: String
        let status: Int
        let details: String?
    }
    let error: Inner
}
