import XCTest
@testable import HermesVoice

final class HermesVoiceTests: XCTestCase {
    func testDefaultConfigUsesPublicBackend() {
        let defaults = UserDefaults(suiteName: "HermesVoiceTests-\(UUID().uuidString)")!
        let config = AppConfig.load(userDefaults: defaults)

        XCTAssertEqual(config.baseURL.absoluteString, "https://hermes-voice.dashanddata.com")
        XCTAssertEqual(config.voiceWebSocketURL.absoluteString, "wss://hermes-voice.dashanddata.com/ws/voice")
        XCTAssertTrue(config.isVoiceFlowAllowed)
    }

    func testConfigRejectsLocalhostOverride() {
        let defaults = UserDefaults(suiteName: "HermesVoiceTests-\(UUID().uuidString)")!
        defaults.set("http://127.0.0.1:8700", forKey: AppConfig.settingsOverrideKey)

        let config = AppConfig.load(userDefaults: defaults)

        #if DEBUG
        XCTAssertTrue(config.isVoiceFlowAllowed)
        XCTAssertEqual(config.voiceWebSocketURL.absoluteString, "ws://127.0.0.1:8700/ws/voice")
        #else
        XCTAssertFalse(config.isVoiceFlowAllowed)
        XCTAssertEqual(config.refusalReason, "Backend origin must use HTTPS.")
        #endif
    }

    func testConfigLoadsDeveloperBearerToken() {
        let defaults = UserDefaults(suiteName: "HermesVoiceTests-\(UUID().uuidString)")!
        defaults.set("test-api-key", forKey: AppConfig.developerBearerTokenKey)

        let config = AppConfig.load(userDefaults: defaults)

        XCTAssertEqual(config.developerBearerToken, "test-api-key")
    }

    func testWavEncoderProducesRiffWav() {
        let data = WavEncoder.pcm16Wav(samples: [0, 0.5, -0.5], sampleRate: 16000)

        XCTAssertEqual(String(data: data.prefix(4), encoding: .ascii), "RIFF")
        XCTAssertEqual(String(data: data.dropFirst(8).prefix(4), encoding: .ascii), "WAVE")
        XCTAssertEqual(String(data: data.dropFirst(12).prefix(4), encoding: .ascii), "fmt ")
        XCTAssertEqual(String(data: data.dropFirst(36).prefix(4), encoding: .ascii), "data")
        XCTAssertEqual(data.count, 44 + 6)
    }
}
