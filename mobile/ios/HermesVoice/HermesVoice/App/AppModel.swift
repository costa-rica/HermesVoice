import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    @Published var scenePhase: ScenePhase = .active
    @Published var developerSettings = DeveloperSettingsStore()

    let sessionStore: SessionStore

    var appConfig: AppConfig {
        AppConfig.current(overrideURLString: developerSettings.backendOverride)
    }

    init() {
        let settings = DeveloperSettingsStore()
        let config = AppConfig.current(overrideURLString: settings.backendOverride)
        sessionStore = SessionStore(authClient: AuthClient(baseURL: config.apiBaseURL))
        developerSettings = settings
    }
}
