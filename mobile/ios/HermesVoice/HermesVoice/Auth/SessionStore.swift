import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var isAuthenticated: Bool = false
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var isInitialCheckDone: Bool = false

    private let authClient: AuthClient

    init(authClient: AuthClient) {
        self.authClient = authClient
    }

    // Called on app launch; sets isAuthenticated and marks isInitialCheckDone.
    func checkSession() async {
        isLoading = true
        defer {
            isLoading = false
            isInitialCheckDone = true
        }
        do {
            isAuthenticated = try await authClient.checkSession()
        } catch {
            isAuthenticated = false
        }
    }

    // Returns the challenge_id on success; throws AuthError on failure.
    func login(email: String, password: String) async throws -> String {
        isLoading = true
        defer { isLoading = false }
        return try await authClient.login(email: email, password: password)
    }

    // Submits the 2FA code; sets isAuthenticated = true on success.
    func verify(challengeID: String, code: String) async throws {
        isLoading = true
        defer { isLoading = false }
        try await authClient.verify(challengeID: challengeID, code: code)
        isAuthenticated = true
    }

    // Clears session regardless of network errors.
    func logout() async {
        isLoading = true
        defer { isLoading = false }
        try? await authClient.logout()
        isAuthenticated = false
    }
}
