import SwiftUI

struct ConversationView: View {
    let appConfig: AppConfig

    @StateObject private var vm: ConversationViewModel
    @EnvironmentObject private var sessionStore: SessionStore
    @Environment(\.scenePhase) private var scenePhase

    init(appConfig: AppConfig) {
        self.appConfig = appConfig
        _vm = StateObject(wrappedValue: ConversationViewModel(appConfig: appConfig))
    }

    var body: some View {
        VStack(spacing: 0) {
            connectionBanner

            if vm.micPermissionDenied {
                micDeniedBanner
            }

            if vm.messages.isEmpty {
                Spacer()
                Text("Hold the button and speak to start a conversation.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                Spacer()
            } else {
                messageList
            }

            ActiveStateBar(state: vm.activeState)

            if vm.activeState != .idle && !vm.isCapturing {
                cancelButton
                    .padding(.top, 12)
            }

            pttButton
                .padding(.bottom, 32)
                .padding(.top, vm.activeState != .idle && !vm.isCapturing ? 8 : 16)
        }
        .navigationTitle("HermesVoice")
        .task {
            vm.connect(config: appConfig)
        }
        .onDisappear {
            vm.disconnect()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase != .active {
                Task { await vm.handleBackground() }
            }
        }
        .onChange(of: vm.authExpired) { _, expired in
            if expired { Task { await sessionStore.logout() } }
        }
    }

    // MARK: - Message list

    private var messageList: some View {
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

    // MARK: - PTT button

    private var pttButton: some View {
        ZStack {
            Circle()
                .fill(pttColor)
                .frame(width: 80, height: 80)
                .shadow(color: pttColor.opacity(0.4), radius: vm.isCapturing ? 12 : 4)

            Image(systemName: vm.isCapturing ? "waveform" : "mic.fill")
                .font(.title)
                .foregroundStyle(.white)
        }
        .animation(.easeInOut(duration: 0.15), value: vm.isCapturing)
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    if !vm.isCapturing {
                        Task { await vm.startPTT() }
                    }
                }
                .onEnded { _ in
                    Task { await vm.stopPTT() }
                }
        )
        .disabled(vm.socket.connectionState != .connected)
        .opacity(vm.socket.connectionState == .connected ? 1 : 0.4)
        .accessibilityLabel(vm.isCapturing ? "Recording — release to send" : "Hold to talk")
    }

    private var cancelButton: some View {
        Button {
            Task { await vm.cancelTurn() }
        } label: {
            Label("Cancel", systemImage: "xmark.circle.fill")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
        .animation(.easeInOut(duration: 0.2), value: vm.activeState)
    }

    private var pttColor: Color {
        vm.isCapturing ? .red : .accentColor
    }

    // MARK: - Banners

    private var connectionBanner: some View {
        Group {
            switch vm.socket.connectionState {
            case .connecting:
                banner("Connecting…", icon: "wifi", color: .orange)
            case .failed:
                banner("Connection failed — tap to retry", icon: "wifi.slash", color: .red)
                    .onTapGesture { vm.reconnect() }
            case .authFailed:
                banner("Session expired — please sign in again", icon: "lock.slash", color: .red)
            case .disconnected:
                banner("Disconnected", icon: "wifi.slash", color: .secondary)
            case .connected:
                EmptyView()
            }
        }
    }

    private var micDeniedBanner: some View {
        banner(
            "Microphone access denied — enable in Settings",
            icon: "mic.slash",
            color: .red
        )
    }

    private func banner(_ text: String, icon: String, color: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(text).font(.footnote)
            Spacer()
        }
        .foregroundStyle(color)
        .padding(.horizontal)
        .padding(.vertical, 6)
        .background(color.opacity(0.1))
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

// MARK: - Active-state bar

private struct ActiveStateBar: View {
    let state: ActiveState

    var body: some View {
        if state != .idle {
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.8)
                Text(label).font(.footnote).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(.regularMaterial)
        }
    }

    private var label: String {
        switch state {
        case .idle:             return ""
        case .listening:        return "Listening…"
        case .thinking,
             .thinkingProgress: return "Thinking…"
        case .speaking:         return "Speaking…"
        case .awaitingApproval: return "Awaiting approval…"
        }
    }
}
