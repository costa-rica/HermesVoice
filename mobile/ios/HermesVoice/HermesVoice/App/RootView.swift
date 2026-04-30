import SwiftUI

struct RootView: View {
    @EnvironmentObject private var appModel: AppModel

    var body: some View {
        NavigationStack {
            ConversationView(
                appConfig: AppConfig.current(
                    overrideURLString: appModel.developerSettings.backendOverride
                )
            )
            #if DEBUG
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink {
                        SettingsView()
                            .environmentObject(appModel)
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            #endif
        }
    }
}
