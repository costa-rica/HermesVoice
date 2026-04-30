import Foundation

struct DeveloperSettingsStore: Equatable {
    private enum Keys {
        static let backendOverride = "HermesVoice.DebugBackendOverride"
    }

    var backendOverride: String {
        didSet {
            UserDefaults.standard.set(backendOverride, forKey: Keys.backendOverride)
        }
    }

    init() {
        backendOverride = UserDefaults.standard.string(forKey: Keys.backendOverride) ?? ""
    }

    mutating func reset() {
        backendOverride = ""
        UserDefaults.standard.removeObject(forKey: Keys.backendOverride)
    }
}
