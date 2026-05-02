import Foundation
import os

struct AppConfig: Equatable {
    static let defaultOrigin = "https://hermes-voice.dashanddata.com"
    static let settingsOverrideKey = "HermesVoice.backendOrigin"
    static let developerBearerTokenKey = "HermesVoice.developerBearerToken"

    let origin: URL
    let developerBearerToken: String?
    let isVoiceFlowAllowed: Bool
    let refusalReason: String?

    var baseURL: URL {
        origin
    }

    var voiceWebSocketURL: URL {
        var components = URLComponents(url: origin, resolvingAgainstBaseURL: false)!
        components.scheme = origin.scheme?.lowercased() == "http" ? "ws" : "wss"
        components.path = "/ws/voice"
        components.query = nil
        components.fragment = nil
        return components.url!
    }

    static func load(userDefaults: UserDefaults = .standard) -> AppConfig {
        let logger = Logger(subsystem: "com.dashanddata.HermesVoice", category: "config")
        let configured = userDefaults.string(forKey: settingsOverrideKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let developerBearerToken = userDefaults.string(forKey: developerBearerTokenKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty
        let originString = configured?.isEmpty == false ? configured! : defaultOrigin

        guard let url = URL(string: originString), let scheme = url.scheme?.lowercased(), let host = url.host else {
            let fallback = URL(string: defaultOrigin)!
            logger.error("Invalid backend origin: \(originString, privacy: .public)")
            return AppConfig(origin: fallback, developerBearerToken: developerBearerToken, isVoiceFlowAllowed: false, refusalReason: "Invalid backend origin.")
        }

        let normalized = URL(string: "\(scheme)://\(host)\(url.port.map { ":\($0)" } ?? "")") ?? url
        if scheme != "https" && !allowsDebugLocalOrigin(scheme: scheme, host: host) {
            logger.error("Refusing non-HTTPS backend origin: \(originString, privacy: .public)")
            return AppConfig(origin: normalized, developerBearerToken: developerBearerToken, isVoiceFlowAllowed: false, refusalReason: "Backend origin must use HTTPS.")
        }

        if isLocalOrLan(host: host) && !allowsDebugLocalOrigin(scheme: scheme, host: host) {
            logger.error("Refusing local/LAN backend origin: \(originString, privacy: .public)")
            return AppConfig(origin: normalized, developerBearerToken: developerBearerToken, isVoiceFlowAllowed: false, refusalReason: "Backend origin cannot be localhost or LAN.")
        }

        logger.info("Using backend origin: \(normalized.absoluteString, privacy: .public)")
        return AppConfig(origin: normalized, developerBearerToken: developerBearerToken, isVoiceFlowAllowed: true, refusalReason: nil)
    }

    private static func isLocalOrLan(host: String) -> Bool {
        let lower = host.lowercased()
        if lower == "localhost" || lower == "127.0.0.1" || lower == "::1" {
            return true
        }

        let parts = lower.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4 else {
            return false
        }

        if parts[0] == 10 {
            return true
        }
        if parts[0] == 192 && parts[1] == 168 {
            return true
        }
        if parts[0] == 172 && (16...31).contains(parts[1]) {
            return true
        }
        if parts[0] == 169 && parts[1] == 254 {
            return true
        }
        return false
    }

    private static func allowsDebugLocalOrigin(scheme: String, host: String) -> Bool {
        #if DEBUG
        return scheme == "http" && isLocalOrLan(host: host)
        #else
        return false
        #endif
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
