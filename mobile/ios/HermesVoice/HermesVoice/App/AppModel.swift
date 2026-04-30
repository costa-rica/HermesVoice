import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    @Published var scenePhase: ScenePhase = .active
    @Published var developerSettings = DeveloperSettingsStore()
}
