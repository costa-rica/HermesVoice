import SwiftUI

struct ConversationView: View {
    let appConfig: AppConfig

    @StateObject private var vm: ConversationViewModel

    init(appConfig: AppConfig) {
        self.appConfig = appConfig
        _vm = StateObject(wrappedValue: ConversationViewModel(appConfig: appConfig))
    }

    var body: some View {
        VStack(spacing: 0) {
            connectionBanner

            if vm.messages.isEmpty {
                Spacer()
                Text("Hold the button and speak to start a conversation.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                Spacer()
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(vm.messages) { message in
                                MessageBubble(message: message)
                                    .id(message.id)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: vm.messages.count) { _, _ in
                        if let last = vm.messages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }
            }

            ActiveStateBar(state: vm.activeState)
        }
        .navigationTitle("HermesVoice")
        .task {
            vm.connect(config: appConfig)
        }
        .onDisappear {
            vm.disconnect()
        }
    }

    private var connectionBanner: some View {
        Group {
            switch vm.socket.connectionState {
            case .connecting:
                banner("Connecting…", color: .orange)
            case .failed:
                banner("Connection failed — check your network", color: .red)
            case .authFailed:
                banner("Authentication failed — please sign in again", color: .red)
            case .disconnected:
                banner("Disconnected", color: .secondary)
            case .connected:
                EmptyView()
            }
        }
    }

    private func banner(_ text: String, color: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "wifi.slash")
            Text(text).font(.footnote)
        }
        .foregroundStyle(color)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(color.opacity(0.08))
    }
}

// MARK: - Message bubble

private struct MessageBubble: View {
    let message: ConversationMessage

    var body: some View {
        HStack {
            if message.role == .assistant { Spacer(minLength: 48) }
            Text(message.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(message.role == .user ? Color.accentColor : Color(.systemGray5))
                .foregroundStyle(message.role == .user ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            if message.role == .user { Spacer(minLength: 48) }
        }
    }
}

// MARK: - Active-state indicator

private struct ActiveStateBar: View {
    let state: ActiveState

    var body: some View {
        if state != .idle {
            HStack(spacing: 8) {
                ProgressView()
                    .scaleEffect(0.8)
                Text(stateLabel)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(.regularMaterial)
        }
    }

    private var stateLabel: String {
        switch state {
        case .idle:              return ""
        case .listening:         return "Listening…"
        case .thinking:          return "Thinking…"
        case .thinkingProgress:  return "Thinking…"
        case .speaking:          return "Speaking…"
        case .awaitingApproval:  return "Awaiting approval…"
        }
    }
}
