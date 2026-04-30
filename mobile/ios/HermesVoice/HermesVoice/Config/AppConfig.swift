import Foundation

struct AppConfig: Equatable {
    let apiBaseURL: URL
    let webSocketURL: URL
    let allowsDeveloperOverride: Bool
    let allowsDeveloperBearerBridge: Bool

    static let productionOrigin = URL(string: "https://hermes-voice.dashanddata.com")!

    static func current(overrideURLString: String?) -> AppConfig {
        #if DEBUG
        if let overrideURLString,
           let overrideURL = sanitizedDebugURL(from: overrideURLString) {
            return AppConfig(
                apiBaseURL: overrideURL,
                webSocketURL: derivedWebSocketURL(from: overrideURL),
                allowsDeveloperOverride: true,
                allowsDeveloperBearerBridge: true
            )
        }
        #endif

        return AppConfig(
            apiBaseURL: productionOrigin,
            webSocketURL: derivedWebSocketURL(from: productionOrigin),
            allowsDeveloperOverride: false,
            allowsDeveloperBearerBridge: false
        )
    }

    static func derivedWebSocketURL(from apiBaseURL: URL) -> URL {
        var components = URLComponents(url: apiBaseURL, resolvingAgainstBaseURL: false)!
        components.scheme = (components.scheme == "https") ? "wss" : "ws"
        components.path = "/ws/voice"
        components.query = nil
        components.fragment = nil
        return components.url!
    }

    #if DEBUG
    private static func sanitizedDebugURL(from rawValue: String) -> URL? {
        guard let url = URL(string: rawValue.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = url.scheme?.lowercased(),
              ["https", "http"].contains(scheme),
              url.host?.isEmpty == false else {
            return nil
        }
        return url
    }
    #endif
}
