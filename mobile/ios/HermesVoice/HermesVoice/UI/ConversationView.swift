import SwiftUI

struct ConversationView: View {
    let appConfig: AppConfig

    var body: some View {
        List {
            Section("Connection") {
                LabeledContent("Backend", value: appConfig.apiBaseURL.absoluteString)
                LabeledContent("Voice WebSocket", value: appConfig.webSocketURL.absoluteString)
                LabeledContent(
                    "Debug bearer bridge",
                    value: appConfig.allowsDeveloperBearerBridge ? "Permitted" : "Not permitted"
                )
                Text("Public HermesVoice origin is the default mobile integration target.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Status") {
                ConnectionStatusView()
                Text("Login and live voice wiring land in the next phases once the mobile auth and downlink backend contracts are available.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("HermesVoice")
    }
}
