import XCTest
@testable import HermesVoice

// MARK: - AppConfig tests

final class AppConfigTests: XCTestCase {
    func testProductionOriginUsesSecureWebSocket() {
        let config = AppConfig.current(overrideURLString: nil)
        XCTAssertEqual(config.apiBaseURL.absoluteString, "https://hermes-voice.dashanddata.com")
        XCTAssertEqual(config.webSocketURL.absoluteString, "wss://hermes-voice.dashanddata.com/ws/voice")
        XCTAssertFalse(config.allowsDeveloperBearerBridge)
    }
}

// MARK: - AuthClient tests via mock URLProtocol

final class AuthClientTests: XCTestCase {
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)
        MockURLProtocol.handler = nil
    }

    override func tearDown() {
        MockURLProtocol.handler = nil
        super.tearDown()
    }

    private func client() -> AuthClient {
        AuthClient(
            baseURL: URL(string: "https://hermes-voice.dashanddata.com")!,
            session: session
        )
    }

    // MARK: login

    func testLoginSuccessReturnsChallengeID() async throws {
        MockURLProtocol.handler = { _ in
            let body = #"{"challenge_id":"abc-123"}"#
            return (200, body.data(using: .utf8)!)
        }
        let id = try await client().login(email: "a@b.com", password: "pw")
        XCTAssertEqual(id, "abc-123")
    }

    func testLoginInvalidCredentialsThrows() async {
        MockURLProtocol.handler = { _ in (401, Data()) }
        do {
            _ = try await client().login(email: "a@b.com", password: "wrong")
            XCTFail("expected throw")
        } catch AuthError.invalidCredentials {
            // expected
        } catch {
            XCTFail("wrong error: \(error)")
        }
    }

    func testLoginEmailSendFailureThrows() async {
        MockURLProtocol.handler = { _ in (502, Data()) }
        do {
            _ = try await client().login(email: "a@b.com", password: "pw")
            XCTFail("expected throw")
        } catch AuthError.emailSendFailed {
            // expected
        } catch {
            XCTFail("wrong error: \(error)")
        }
    }

    func testLoginRateLimitedThrows() async {
        MockURLProtocol.handler = { _ in (429, Data()) }
        do {
            _ = try await client().login(email: "a@b.com", password: "pw")
            XCTFail("expected throw")
        } catch AuthError.rateLimited {
            // expected
        } catch {
            XCTFail("wrong error: \(error)")
        }
    }

    // MARK: verify

    func testVerifySuccess() async throws {
        MockURLProtocol.handler = { _ in
            (200, #"{"ok":true}"#.data(using: .utf8)!)
        }
        try await client().verify(challengeID: "abc", code: "123456")
    }

    func testVerifyInvalidCodeThrows() async {
        MockURLProtocol.handler = { _ in (401, Data()) }
        do {
            try await client().verify(challengeID: "abc", code: "000000")
            XCTFail("expected throw")
        } catch AuthError.invalidCode {
            // expected
        } catch {
            XCTFail("wrong error: \(error)")
        }
    }

    // MARK: checkSession

    func testCheckSessionAuthenticated() async throws {
        MockURLProtocol.handler = { _ in
            (200, #"{"authenticated":true}"#.data(using: .utf8)!)
        }
        let result = try await client().checkSession()
        XCTAssertTrue(result)
    }

    func testCheckSessionNotAuthenticated() async throws {
        MockURLProtocol.handler = { _ in
            (200, #"{"authenticated":false}"#.data(using: .utf8)!)
        }
        let result = try await client().checkSession()
        XCTAssertFalse(result)
    }

    // MARK: logout

    func testLogoutSuccess() async throws {
        MockURLProtocol.handler = { _ in
            (200, #"{"ok":true}"#.data(using: .utf8)!)
        }
        try await client().logout()
    }

    func testLogoutUnexpectedStatusThrows() async {
        MockURLProtocol.handler = { _ in (500, Data()) }
        do {
            try await client().logout()
            XCTFail("expected throw")
        } catch AuthError.unexpectedResponse(500) {
            // expected
        } catch {
            XCTFail("wrong error: \(error)")
        }
    }
}

// MARK: - MockURLProtocol

final class MockURLProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown))
            return
        }
        let (statusCode, body) = handler(request)
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
