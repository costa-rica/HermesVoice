import SwiftUI

struct VoiceTuningSettings: Equatable {
    var minSilenceDuration: Double
    var speakerBargeInDelay: Double
    var bluetoothBargeInDelay: Double
}

struct ContentView: View {
    @State private var config = AppConfig.load()
    @State private var showsSettings = false
    @State private var showsSessions = false
    @State private var voiceShouldRun = false
    @State private var sessionShouldRun = false
    @StateObject private var authViewModel: AuthViewModel
    @StateObject private var sessionViewModel: VoiceSessionsViewModel
    @AppStorage("voice.minSilenceDuration") private var minSilenceDuration = 1.0
    @AppStorage("voice.speakerBargeInDelay") private var speakerBargeInDelay = 0.45
    @AppStorage("voice.bluetoothBargeInDelay") private var bluetoothBargeInDelay = 0.15

    init() {
        let config = AppConfig.load()
        _config = State(initialValue: config)
        _authViewModel = StateObject(wrappedValue: AuthViewModel(config: config))
        _sessionViewModel = StateObject(wrappedValue: VoiceSessionsViewModel(config: config))
    }

    private var voiceSettings: VoiceTuningSettings {
        VoiceTuningSettings(
            minSilenceDuration: minSilenceDuration,
            speakerBargeInDelay: speakerBargeInDelay,
            bluetoothBargeInDelay: bluetoothBargeInDelay
        )
    }

    var body: some View {
        NavigationStack {
            Group {
                switch authViewModel.state {
                case .checking:
                    ProgressView("Checking session...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .authenticated:
                    VADTestView(
                        config: config,
                        settings: voiceSettings,
                        sessionID: sessionViewModel.selectedSessionID,
                        historyMessages: sessionViewModel.messages,
                        shouldRun: $voiceShouldRun,
                        sessionShouldRun: $sessionShouldRun,
                        onSessionStarted: { frame in
                            sessionViewModel.handleSessionStarted(frame)
                        },
                        onConversationUpdated: {
                            Task {
                                await sessionViewModel.reloadSelectedMessages()
                            }
                        }
                    )
                    .id(sessionViewModel.selectedSessionID ?? "implicit-session")
                        .navigationTitle("HermesVoice")
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button {
                                    showsSessions = true
                                } label: {
                                    Image(systemName: "line.3.horizontal")
                                }
                            }
                            ToolbarItem(placement: .topBarTrailing) {
                                Button {
                                    showsSettings = true
                                } label: {
                                    Image(systemName: "gearshape")
                                }
                            }
                        }
                        .sheet(isPresented: $showsSessions) {
                            VoiceSessionsSheet(viewModel: sessionViewModel)
                        }
                        .sheet(isPresented: $showsSettings) {
                            VoiceSettingsView(
                                minSilenceDuration: $minSilenceDuration,
                                speakerBargeInDelay: $speakerBargeInDelay,
                                bluetoothBargeInDelay: $bluetoothBargeInDelay,
                                onLogout: {
                                    showsSettings = false
                                    showsSessions = false
                                    voiceShouldRun = false
                                    sessionShouldRun = false
                                    Task {
                                        await authViewModel.logout()
                                    }
                                }
                            )
                        }
                case .unauthenticated, .awaitingCode:
                    LoginView(viewModel: authViewModel)
                        .navigationTitle("HermesVoice")
                }
            }
            .task {
                await authViewModel.restoreSession()
            }
            .task(id: authViewModel.state) {
                if authViewModel.state == .authenticated {
                    await sessionViewModel.loadSessions(selectFirstIfNeeded: true)
                }
            }
            .onChange(of: authViewModel.state) { _, state in
                if state != .authenticated {
                    showsSettings = false
                    showsSessions = false
                    voiceShouldRun = false
                    sessionShouldRun = false
                    sessionViewModel.reset()
                }
            }
        }
    }
}

@MainActor
final class AuthViewModel: ObservableObject {
    enum State: Equatable {
        case checking
        case unauthenticated
        case awaitingCode
        case authenticated
    }

    @Published var state: State = .checking
    @Published var email = ""
    @Published var password = ""
    @Published var verificationCode = ""
    @Published var statusMessage = ""
    @Published var isWorking = false
    @Published var mockCode: String?

    private let client: AuthClient
    private var challengeID: String?
    private var didRestoreSession = false

    init(config: AppConfig) {
        client = AuthClient(config: config)
    }

    func restoreSession() async {
        guard !didRestoreSession else { return }
        didRestoreSession = true
        state = .checking
        do {
            state = try await client.checkSession() ? .authenticated : .unauthenticated
        } catch {
            statusMessage = error.localizedDescription
            state = .unauthenticated
        }
    }

    func login() async {
        guard !isWorking else { return }
        isWorking = true
        statusMessage = ""
        mockCode = nil
        defer { isWorking = false }

        do {
            let response = try await client.login(email: email, password: password)
            challengeID = response.challengeID
            mockCode = response.mockCode
            verificationCode = response.mockCode ?? ""
            statusMessage = response.mockCode == nil ? "Enter the verification code sent to your email." : "Mock code received."
            state = .awaitingCode
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func verify() async {
        guard !isWorking, let challengeID else { return }
        isWorking = true
        statusMessage = ""
        defer { isWorking = false }

        do {
            try await client.verify(challengeID: challengeID, code: verificationCode)
            password = ""
            verificationCode = ""
            self.challengeID = nil
            mockCode = nil
            state = .authenticated
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func logout() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            try await client.logout()
        } catch {
            statusMessage = error.localizedDescription
        }
        password = ""
        verificationCode = ""
        challengeID = nil
        state = .unauthenticated
    }

    func backToLogin() {
        verificationCode = ""
        challengeID = nil
        mockCode = nil
        statusMessage = ""
        state = .unauthenticated
    }
}

struct LoginView: View {
    @ObservedObject var viewModel: AuthViewModel

    var body: some View {
        Form {
            if viewModel.state == .awaitingCode {
                Section {
                    TextField("Verification code", text: $viewModel.verificationCode)
                        .textContentType(.oneTimeCode)
                        .keyboardType(.numberPad)
                    if let mockCode = viewModel.mockCode {
                        Text("Mock code: \(mockCode)")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
                Section {
                    Button {
                        Task {
                            await viewModel.verify()
                        }
                    } label: {
                        if viewModel.isWorking {
                            ProgressView()
                        } else {
                            Text("Verify")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(viewModel.isWorking || viewModel.verificationCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    Button("Use a different email") {
                        viewModel.backToLogin()
                    }
                }
            } else {
                Section {
                    TextField("Email", text: $viewModel.email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $viewModel.password)
                        .textContentType(.password)
                }
                Section {
                    Button {
                        Task {
                            await viewModel.login()
                        }
                    } label: {
                        if viewModel.isWorking {
                            ProgressView()
                        } else {
                            Text("Continue")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(viewModel.isWorking || viewModel.email.isEmpty || viewModel.password.isEmpty)
                }
            }

            if !viewModel.statusMessage.isEmpty {
                Section {
                    Text(viewModel.statusMessage)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

@MainActor
final class VoiceSessionsViewModel: ObservableObject {
    @Published var sessions: [VoiceSessionRecord] = []
    @Published var selectedSessionID: String?
    @Published var messages: [VoiceMessageRecord] = []
    @Published var isLoading = false
    @Published var statusMessage = ""

    private let client: VoiceSessionClient
    private let selectedSessionKey = "voice.selectedSessionID"

    init(config: AppConfig) {
        client = VoiceSessionClient(config: config)
        selectedSessionID = UserDefaults.standard.string(forKey: selectedSessionKey)
    }

    func reset() {
        sessions = []
        setSelectedSessionID(nil)
        messages = []
        isLoading = false
        statusMessage = ""
    }

    func loadSessions(selectFirstIfNeeded: Bool) async {
        guard !isLoading else { return }
        isLoading = true
        statusMessage = ""
        defer { isLoading = false }

        do {
            let loaded = try await client.listSessions()
            sessions = loaded
            if selectedSessionID == nil, selectFirstIfNeeded {
                if let first = loaded.first {
                    await selectSession(first.id)
                } else {
                    try await createSessionRecord()
                }
            } else if let selectedSessionID, !loaded.contains(where: { $0.id == selectedSessionID }) {
                setSelectedSessionID(loaded.first?.id)
                await reloadSelectedMessages()
            }
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func createSession() async {
        guard !isLoading else { return }
        isLoading = true
        statusMessage = ""
        defer { isLoading = false }

        do {
            try await createSessionRecord()
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func selectSession(_ id: String) async {
        setSelectedSessionID(id)
        await reloadSelectedMessages()
    }

    func reloadSelectedMessages() async {
        guard let selectedSessionID else {
            messages = []
            return
        }

        do {
            messages = try await client.loadMessages(sessionID: selectedSessionID)
            if let index = sessions.firstIndex(where: { $0.id == selectedSessionID }) {
                let refreshed = try? await client.listSessions()
                if let refreshedSession = refreshed?.first(where: { $0.id == selectedSessionID }) {
                    sessions[index] = refreshedSession
                }
            }
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func archiveSession(_ id: String) async {
        do {
            try await client.archiveSession(sessionID: id)
            sessions.removeAll { $0.id == id }
            if selectedSessionID == id {
                setSelectedSessionID(sessions.first?.id)
                await reloadSelectedMessages()
            }
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func handleSessionStarted(_ frame: ServerFrame) {
        guard let sessionID = frame.sessionID else { return }
        setSelectedSessionID(sessionID)
        if !sessions.contains(where: { $0.id == sessionID }) {
            Task {
                await loadSessions(selectFirstIfNeeded: false)
            }
        }
    }

    private func createSessionRecord() async throws {
        let session = try await client.createSession()
        sessions.insert(session, at: 0)
        setSelectedSessionID(session.id)
        messages = []
    }

    private func setSelectedSessionID(_ id: String?) {
        selectedSessionID = id
        if let id {
            UserDefaults.standard.set(id, forKey: selectedSessionKey)
        } else {
            UserDefaults.standard.removeObject(forKey: selectedSessionKey)
        }
    }
}

struct VoiceSessionsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var viewModel: VoiceSessionsViewModel

    var body: some View {
        NavigationStack {
            List {
                if !viewModel.statusMessage.isEmpty {
                    Section {
                        Text(viewModel.statusMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Button {
                        Task {
                            await viewModel.createSession()
                            dismiss()
                        }
                    } label: {
                        Label("New Session", systemImage: "plus")
                    }
                }

                Section {
                    if viewModel.sessions.isEmpty && viewModel.isLoading {
                        ProgressView()
                    } else if viewModel.sessions.isEmpty {
                        Text("No sessions yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.sessions) { session in
                            Button {
                                Task {
                                    await viewModel.selectSession(session.id)
                                    dismiss()
                                }
                            } label: {
                                HStack(alignment: .top, spacing: 10) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(session.displayTitle)
                                            .lineLimit(2)
                                        if let preview = session.lastMessagePreview, preview != session.displayTitle {
                                            Text(preview)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(2)
                                        }
                                        Text("\(session.messageCount) messages")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if viewModel.selectedSessionID == session.id {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(.blue)
                                    }
                                }
                            }
                        }
                        .onDelete { offsets in
                            for offset in offsets {
                                let id = viewModel.sessions[offset].id
                                Task {
                                    await viewModel.archiveSession(id)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Sessions")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Refresh") {
                        Task {
                            await viewModel.loadSessions(selectFirstIfNeeded: false)
                        }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .task {
                await viewModel.loadSessions(selectFirstIfNeeded: false)
            }
        }
    }
}

struct VoiceSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var minSilenceDuration: Double
    @Binding var speakerBargeInDelay: Double
    @Binding var bluetoothBargeInDelay: Double
    let onLogout: () -> Void

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

                Section {
                    Button("Log Out", role: .destructive) {
                        onLogout()
                    }
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
