import SwiftUI

struct ContentView: View {
    @State private var config = AppConfig.load()

    var body: some View {
        NavigationStack {
            VADTestView(config: config)
                .navigationTitle("HermesVoice")
                .toolbar {
                    Button("Reload") {
                        config = AppConfig.load()
                    }
                }
        }
    }
}

#Preview {
    ContentView()
}
