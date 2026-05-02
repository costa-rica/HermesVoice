import SwiftUI

struct VoiceTuningSettings: Equatable {
    var minSilenceDuration: Double
    var speakerBargeInDelay: Double
    var bluetoothBargeInDelay: Double
}

struct ContentView: View {
    @State private var config = AppConfig.load()
    @State private var showsSettings = false
    @AppStorage("voice.minSilenceDuration") private var minSilenceDuration = 1.0
    @AppStorage("voice.speakerBargeInDelay") private var speakerBargeInDelay = 0.45
    @AppStorage("voice.bluetoothBargeInDelay") private var bluetoothBargeInDelay = 0.15

    private var voiceSettings: VoiceTuningSettings {
        VoiceTuningSettings(
            minSilenceDuration: minSilenceDuration,
            speakerBargeInDelay: speakerBargeInDelay,
            bluetoothBargeInDelay: bluetoothBargeInDelay
        )
    }

    var body: some View {
        NavigationStack {
            VADTestView(config: config, settings: voiceSettings)
                .navigationTitle("HermesVoice")
                .toolbar {
                    Button {
                        showsSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
                .sheet(isPresented: $showsSettings) {
                    VoiceSettingsView(
                        minSilenceDuration: $minSilenceDuration,
                        speakerBargeInDelay: $speakerBargeInDelay,
                        bluetoothBargeInDelay: $bluetoothBargeInDelay
                    )
                }
        }
    }
}

struct VoiceSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var minSilenceDuration: Double
    @Binding var speakerBargeInDelay: Double
    @Binding var bluetoothBargeInDelay: Double

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    tuningSlider(
                        title: "Pause before sending",
                        value: $minSilenceDuration,
                        range: 0.3 ... 2.0,
                        step: 0.1,
                        help: "Longer values give you more room for brief pauses while speaking."
                    )
                }

                Section {
                    tuningSlider(
                        title: "Speaker barge-in",
                        value: $speakerBargeInDelay,
                        range: 0.15 ... 1.2,
                        step: 0.05,
                        help: "Longer values reduce accidental interruption from speaker playback."
                    )
                    tuningSlider(
                        title: "Bluetooth barge-in",
                        value: $bluetoothBargeInDelay,
                        range: 0.05 ... 0.8,
                        step: 0.05,
                        help: "Shorter values make interrupting easier with headphones."
                    )
                }
            }
            .navigationTitle("Voice Settings")
            .toolbar {
                Button("Done") {
                    dismiss()
                }
            }
        }
    }

    private func tuningSlider(
        title: String,
        value: Binding<Double>,
        range: ClosedRange<Double>,
        step: Double,
        help: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                Spacer()
                Text(String(format: "%.2fs", value.wrappedValue))
                    .font(.body.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Slider(value: value, in: range, step: step)
            Text(help)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    ContentView()
}
