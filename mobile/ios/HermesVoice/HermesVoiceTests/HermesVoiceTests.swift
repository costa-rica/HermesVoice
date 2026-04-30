import XCTest
@testable import HermesVoice

final class HermesVoiceTests: XCTestCase {
    func testProductionOriginUsesSecureWebSocket() {
        let config = AppConfig.current(overrideURLString: nil)

        XCTAssertEqual(config.apiBaseURL.absoluteString, "https://hermes-voice.dashanddata.com")
        XCTAssertEqual(config.webSocketURL.absoluteString, "wss://hermes-voice.dashanddata.com/ws/voice")
        XCTAssertFalse(config.allowsDeveloperBearerBridge)
    }
}
