import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var appModel: AppModel

    var body: some View {
        Form {
            Section("Backend") {
                TextField(
                    "https://hermes-voice.dashanddata.com",
                    text: $appModel.developerSettings.backendOverride
                )
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()

                Button("Reset to public backend") {
                    appModel.developerSettings.reset()
                }
            }

            Section("Effective configuration") {
                let config = AppConfig.current(
                    overrideURLString: appModel.developerSettings.backendOverride
                )
                LabeledContent("API origin", value: config.apiBaseURL.absoluteString)
                LabeledContent("Voice socket", value: config.webSocketURL.absoluteString)
                LabeledContent(
                    "Bearer dev bridge",
                    value: config.allowsDeveloperBearerBridge ? "Available in Debug" : "Disabled"
                )
            }
        }
        .navigationTitle("Settings")
    }
}
