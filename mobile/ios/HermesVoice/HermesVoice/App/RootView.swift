import SwiftUI

struct RootView: View {
    @EnvironmentObject private var appModel: AppModel
    @EnvironmentObject private var sessionStore: SessionStore

    var body: some View {
        Group {
            if !sessionStore.isInitialCheckDone {
                ProgressView("Connecting…")
            } else if sessionStore.isAuthenticated {
                NavigationStack {
                    ConversationView(appConfig: appModel.appConfig)
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button("Sign Out") {
                                    Task { await sessionStore.logout() }
                                }
                                .foregroundStyle(.red)
                            }
                            #if DEBUG
                            ToolbarItem(placement: .topBarTrailing) {
                                NavigationLink {
                                    SettingsView()
                                        .environmentObject(appModel)
                                } label: {
                                    Image(systemName: "gearshape")
                                }
                            }
                            #endif
                        }
                }
            } else {
                NavigationStack {
                    LoginView()
                }
            }
        }
        .task {
            await sessionStore.checkSession()
        }
    }
}
