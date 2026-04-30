import SwiftUI

@main
struct HermesVoiceApp: App {
    @StateObject private var appModel = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appModel)
                .onChange(of: scenePhase) { _, newPhase in
                    appModel.scenePhase = newPhase
                }
        }
    }
}
