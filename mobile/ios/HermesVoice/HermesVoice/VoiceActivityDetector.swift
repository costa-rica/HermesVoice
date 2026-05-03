import AVFoundation
import Foundation
import os
import SwiftUI

enum VADEvent: Equatable {
    case started(at: TimeInterval)
    case ended(at: TimeInterval, duration: TimeInterval, samples: [Float])
    case stateChanged(isSpeaking: Bool)
    case message(String)
}

private final class OneShotAudioBufferProvider {
    private var buffer: AVAudioPCMBuffer?

    init(buffer: AVAudioPCMBuffer) {
        self.buffer = buffer
    }

    func provide(_ outStatus: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
        guard let next = buffer else {
            outStatus.pointee = .noDataNow
            return nil
        }

        buffer = nil
        outStatus.pointee = .haveData
        return next
    }
}

actor VoiceActivityDetector {
    private let sampleRate = 16000
    private let logger = Logger(subsystem: "com.dashanddata.HermesVoice", category: "vad")

    private var settings: VoiceTuningSettings
    private var audioEngine: AVAudioEngine?
    private var audioSession = AVAudioSession.sharedInstance()
    private var vadModelConfig: SherpaOnnxVadModelConfig?
    private var vad: SherpaOnnxVoiceActivityDetectorWrapper?
    private var pendingSamples: [Float] = []
    private var processedSamples = 0
    private var speechStartSamples: Int?
    private var continuation: AsyncStream<VADEvent>.Continuation?

    init(settings: VoiceTuningSettings = VoiceTuningSettings(
        minSilenceDuration: 1.0,
        speakerBargeInDelay: 0.45,
        bluetoothBargeInDelay: 0.15
    )) {
        self.settings = settings
    }

    func updateSettings(_ settings: VoiceTuningSettings) {
        guard self.settings != settings else { return }
        self.settings = settings
        setupVad()
        continuation?.yield(.message(String(format: "Voice settings updated: pause %.2fs", settings.minSilenceDuration)))
    }

    func events() -> AsyncStream<VADEvent> {
        AsyncStream { continuation in
            self.continuation = continuation
            continuation.onTermination = { [weak self] _ in
                Task {
                    await self?.stop()
                }
            }
        }
    }

    func prepare() {
        setupVad()
        setupAudioSession()
        setupRecorder()
    }

    func start() throws {
        if audioEngine == nil || vad == nil {
            prepare()
        }

        pendingSamples.removeAll()
        processedSamples = 0
        speechStartSamples = nil
        vad?.reset()
        continuation?.yield(.stateChanged(isSpeaking: false))
        continuation?.yield(.message("Started microphone VAD."))

        try audioSession.setActive(true)
        try audioEngine?.start()
        logger.info("VAD audio engine started")
    }

    func stop() {
        audioEngine?.stop()
        vad?.flush()
        drainCompletedSegments()
        continuation?.yield(.stateChanged(isSpeaking: false))
        continuation?.yield(.message("Stopped microphone VAD."))
        logger.info("VAD audio engine stopped")
    }

    private func setupVad() {
        let sileroVadConfig = sherpaOnnxSileroVadModelConfig(
            model: resourcePath("silero_vad", "onnx"),
            threshold: 0.5,
            minSilenceDuration: Float(settings.minSilenceDuration),
            minSpeechDuration: 0.25,
            windowSize: 512,
            maxSpeechDuration: 30.0
        )

        var config = sherpaOnnxVadModelConfig(
            sileroVad: sileroVadConfig,
            sampleRate: Int32(sampleRate),
            numThreads: 1,
            provider: "cpu"
        )
        vadModelConfig = config
        vad = SherpaOnnxVoiceActivityDetectorWrapper(config: &config, buffer_size_in_seconds: 120)
    }

    private func setupAudioSession() {
        do {
            try audioSession.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [.defaultToSpeaker, .allowBluetoothHFP]
            )
            if #available(iOS 18.2, *) {
                try audioSession.setPrefersEchoCancelledInput(true)
            }
            try audioSession.setPreferredSampleRate(Double(sampleRate))
            try audioSession.setActive(true)
        } catch {
            continuation?.yield(.message("Audio session setup failed: \(error.localizedDescription)"))
            logger.error("Audio session setup failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func setupRecorder() {
        audioEngine = AVAudioEngine()

        guard let audioEngine else {
            continuation?.yield(.message("No audio engine available."))
            return
        }

        let inputNode = audioEngine.inputNode
        let bus = 0
        let inputFormat = inputNode.outputFormat(forBus: bus)
        let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: Double(sampleRate),
            channels: 1,
            interleaved: false
        )!

        guard let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            continuation?.yield(.message("Could not create audio converter."))
            return
        }

        inputNode.removeTap(onBus: bus)
        inputNode.installTap(onBus: bus, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            guard let self else { return }
            let bufferProvider = OneShotAudioBufferProvider(buffer: buffer)
            let inputCallback: AVAudioConverterInputBlock = { _, outStatus in
                bufferProvider.provide(outStatus)
            }

            let capacity = AVAudioFrameCount(outputFormat.sampleRate)
                * buffer.frameLength
                / AVAudioFrameCount(buffer.format.sampleRate)
            guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
                return
            }

            var error: NSError?
            _ = converter.convert(to: convertedBuffer, error: &error, withInputFrom: inputCallback)
            if let error {
                Task {
                    await self.emit("Audio convert failed: \(error.localizedDescription)")
                }
                return
            }

            let samples = convertedBuffer.floatArray()
            Task {
                await self.process(samples: samples)
            }
        }
    }

    private func process(samples: [Float]) {
        guard let vadModelConfig, let vad, !samples.isEmpty else { return }

        pendingSamples.append(contentsOf: samples)
        let windowSize = Int(vadModelConfig.silero_vad.window_size)

        while pendingSamples.count >= windowSize {
            let window = Array(pendingSamples[0 ..< windowSize])
            pendingSamples.removeFirst(windowSize)
            vad.acceptWaveform(samples: window)
            processedSamples += windowSize

            let detected = vad.isSpeechDetected()
            if detected && speechStartSamples == nil {
                speechStartSamples = processedSamples
                let startedAt = seconds(processedSamples)
                continuation?.yield(.started(at: startedAt))
                continuation?.yield(.stateChanged(isSpeaking: true))
                logger.info("Speech start at \(startedAt, privacy: .public)s")
            } else if !detected && speechStartSamples == nil {
                continuation?.yield(.stateChanged(isSpeaking: false))
            }

            drainCompletedSegments()
        }
    }

    private func drainCompletedSegments() {
        guard let vad else { return }

        while !vad.isEmpty() {
            let segment = vad.front()
            let start = seconds(segment.start)
            let duration = seconds(segment.samples.count)
            let end = start + duration
            vad.pop()

            speechStartSamples = nil
            continuation?.yield(.ended(at: end, duration: duration, samples: segment.samples))
            continuation?.yield(.stateChanged(isSpeaking: false))
            logger.info("Speech end at \(end, privacy: .public)s duration \(duration, privacy: .public)s")
        }
    }

    private func emit(_ message: String) {
        continuation?.yield(.message(message))
    }

    private func seconds(_ samples: Int) -> TimeInterval {
        TimeInterval(samples) / TimeInterval(sampleRate)
    }

    private func resourcePath(_ name: String, _ ext: String) -> String {
        guard let path = Bundle.main.path(forResource: name, ofType: ext) else {
            preconditionFailure("\(name).\(ext) is missing from the app bundle")
        }
        return path
    }
}

@MainActor
final class VADTestViewModel: ObservableObject {
    @Published var isRunning = false
    @Published var isSessionRunning = false
    @Published var isSpeaking = false
    @Published var isConnected = false
    @Published var lastEvent = "silent"
    @Published var eventLog = "Ready. Press Start and allow microphone access."
    @Published var transcript = ""
    @Published var assistantText = ""
    @Published var downlinkFormat = ""
    @Published var serverState = "idle"
    @Published var playbackStatus = ""
    @Published var audioRouteStatus = "Route: unknown"
    @Published var settings: VoiceTuningSettings
    @Published var historyMessages: [VoiceMessageRecord]

    private let detector: VoiceActivityDetector
    private let socket: VoiceSocket
    private let onSessionStarted: (ServerFrame) -> Void
    private let onConversationUpdated: () -> Void
    private let audioPlayer = AudioPlayer()
    private let audioSession = AVAudioSession.sharedInstance()
    private var eventTask: Task<Void, Never>?
    private var socketTask: Task<Void, Never>?
    private var routeObserver: NSObjectProtocol?
    private var events: [String] = []
    private var downlinkSampleRate = 16000
    private var downlinkChannels = 1
    private var audioRouteUsesBluetooth = false
    private var rawIsSpeaking = false
    private var assistantPlaybackActive = false
    private var playbackGeneration = 0
    private var pipelineGeneration = 0
    private var activeAssistantTurnID: String?
    private var canceledTurnIDs = Set<String>()
    private var bargeInConfirmed = false
    private var bargeCandidateID = 0
    private var bargeCandidateTask: Task<Void, Never>?

    init(
        config: AppConfig,
        settings: VoiceTuningSettings,
        sessionID: String?,
        historyMessages: [VoiceMessageRecord],
        onSessionStarted: @escaping (ServerFrame) -> Void,
        onConversationUpdated: @escaping () -> Void
    ) {
        self.settings = settings
        self.historyMessages = historyMessages
        self.onSessionStarted = onSessionStarted
        self.onConversationUpdated = onConversationUpdated
        detector = VoiceActivityDetector(settings: settings)
        socket = VoiceSocket(config: config, sessionID: sessionID)
        updateAudioRoute(shouldLog: false)
        routeObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: audioSession,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.updateAudioRoute(shouldLog: true)
            }
        }
    }

    func updateSettings(_ settings: VoiceTuningSettings) {
        guard self.settings != settings else { return }
        self.settings = settings
        Task {
            await detector.updateSettings(settings)
        }
        append(String(format: "Settings: pause %.2fs, speaker barge %.2fs, Bluetooth barge %.2fs",
                      settings.minSilenceDuration,
                      settings.speakerBargeInDelay,
                      settings.bluetoothBargeInDelay))
    }

    func updateHistoryMessages(_ messages: [VoiceMessageRecord]) {
        historyMessages = messages
    }

    deinit {
        if let routeObserver {
            NotificationCenter.default.removeObserver(routeObserver)
        }
        eventTask?.cancel()
        socketTask?.cancel()
        let detector = detector
        let audioPlayer = audioPlayer
        let socket = socket
        Task {
            await detector.stop()
            await audioPlayer.stop()
            await socket.disconnect(reason: "view model released")
        }
    }

    func startSession() {
        guard !isSessionRunning else { return }
        pipelineGeneration += 1
        isSessionRunning = true
        events.removeAll()
        eventLog = "Starting session..."
        transcript = ""
        assistantText = ""
        serverState = "idle"
        playbackStatus = ""
        updateAudioRoute(shouldLog: false)
        rawIsSpeaking = false
        assistantPlaybackActive = false
        activeAssistantTurnID = nil
        canceledTurnIDs.removeAll()
        bargeInConfirmed = false
        bargeCandidateTask?.cancel()
        bargeCandidateTask = nil

        socketTask = Task {
            let stream = await socket.events()
            let connectTask = Task {
                await socket.connect()
            }
            defer { connectTask.cancel() }

            for await event in stream {
                handleSocket(event)
            }
        }
    }

    func startVoice() {
        if !isSessionRunning {
            startSession()
        }
        guard !isRunning else { return }
        isRunning = true
        isSpeaking = false
        lastEvent = "silent"
        rawIsSpeaking = false
        bargeInConfirmed = false
        bargeCandidateTask?.cancel()
        bargeCandidateTask = nil
        eventTask = Task {
            let stream = await detector.events()
            await detector.prepare()
            do {
                try await detector.start()
            } catch {
                append("Audio engine start failed: \(error.localizedDescription)")
                isRunning = false
                return
            }

            for await event in stream {
                handle(event)
            }
        }
    }

    func stopVoice() {
        guard isRunning || eventTask != nil else { return }
        isRunning = false
        isSpeaking = false
        lastEvent = "silent"
        rawIsSpeaking = false
        bargeInConfirmed = false
        bargeCandidateTask?.cancel()
        bargeCandidateTask = nil
        eventTask?.cancel()
        eventTask = nil
        Task {
            await detector.stop()
        }
        append("Voice stopped.")
    }

    func stopSession() {
        stopPipeline(reason: "session stopped")
    }

    func shutdownForSessionSwitch() {
        stopPipeline(reason: "session changed")
    }

    private func stopPipeline(reason: String) {
        guard isSessionRunning || isRunning || isConnected || assistantPlaybackActive || eventTask != nil || socketTask != nil else { return }
        pipelineGeneration += 1
        playbackGeneration += 1
        isSessionRunning = false
        isRunning = false
        isConnected = false
        isSpeaking = false
        lastEvent = "silent"
        rawIsSpeaking = false
        assistantPlaybackActive = false
        bargeInConfirmed = false
        activeAssistantTurnID = nil
        bargeCandidateTask?.cancel()
        bargeCandidateTask = nil

        eventTask?.cancel()
        eventTask = nil
        socketTask?.cancel()
        socketTask = nil

        Task {
            await detector.stop()
            await audioPlayer.stop()
            await socket.disconnect(reason: reason)
        }
        append(reason == "session changed" ? "Stopped previous session." : "Session stopped.")
    }

    private func handle(_ event: VADEvent) {
        guard isRunning else { return }
        switch event {
        case .started(let at):
            rawIsSpeaking = true
            if assistantPlaybackActive {
                append(String(format: "Potential barge-in at %.2fs", at))
                scheduleBargeInConfirmation()
            } else {
                isSpeaking = true
                lastEvent = "speaking"
                append(String(format: "Speech start at %.2fs", at))
                checkForLocalPlaybackInterruption(at: at)
            }
        case .ended(let at, let duration, let samples):
            rawIsSpeaking = false
            bargeCandidateTask?.cancel()
            bargeCandidateTask = nil
            append(String(format: "Speech end at %.2fs, duration %.2fs", at, duration))
            if assistantPlaybackActive && !bargeInConfirmed {
                append("Ignored playback-side speech candidate.")
                isSpeaking = false
                lastEvent = "silent"
                return
            }
            Task {
                do {
                    try await socket.sendUtterance(samples: samples)
                    await MainActor.run {
                        append(String(format: "Sent utterance: %.2fs", duration))
                        bargeInConfirmed = false
                    }
                } catch {
                    await MainActor.run {
                        append("Utterance send failed: \(error.localizedDescription)")
                    }
                }
            }
        case .stateChanged(let speaking):
            rawIsSpeaking = speaking
            if !assistantPlaybackActive || bargeInConfirmed {
                isSpeaking = speaking
                lastEvent = speaking ? "speaking" : "silent"
            } else if !speaking {
                isSpeaking = false
                lastEvent = "silent"
            }
        case .message(let message):
            append(message)
        }
    }

    private func handleSocket(_ event: VoiceSocketEvent) {
        guard isSessionRunning else { return }
        switch event {
        case .connected(let frame):
            isConnected = true
            onSessionStarted(frame)
            downlinkFormat = frame.downlinkFormat ?? ""
            downlinkSampleRate = frame.downlinkSampleRate ?? 16000
            downlinkChannels = frame.downlinkChannels ?? 1
            append("Socket connected: \(downlinkFormat)")
        case .frame(let frame):
            handleServerFrame(frame)
        case .audioChunk(let data, let prelude):
            let generation = pipelineGeneration
            let format = prelude.format ?? downlinkFormat
            if let turnID = prelude.turnID, canceledTurnIDs.contains(turnID) {
                append("Ignored canceled audio chunk \(prelude.seq ?? 0): \(turnID)")
                return
            }
            if let turnID = prelude.turnID {
                activeAssistantTurnID = turnID
            }
            append("Audio chunk \(prelude.seq ?? 0): \(data.count) bytes \(format)")
            playbackStatus = "Playing \(format) \(data.count) bytes"
            let playbackToken = markAssistantPlaybackActive(for: data, format: format)
            Task {
                do {
                    guard await MainActor.run(body: {
                        self.isSessionRunning &&
                            self.pipelineGeneration == generation &&
                            self.playbackGeneration == playbackToken
                    }) else { return }
                    try await audioPlayer.play(
                        audio: data,
                        format: format,
                        sampleRate: downlinkSampleRate,
                        channels: downlinkChannels
                    )
                    await MainActor.run {
                        guard self.isSessionRunning &&
                            self.pipelineGeneration == generation &&
                            self.playbackGeneration == playbackToken else { return }
                        playbackStatus = "Queued audio: \(data.count) bytes"
                    }
                } catch {
                    await MainActor.run {
                        guard self.isSessionRunning &&
                            self.pipelineGeneration == generation &&
                            self.playbackGeneration == playbackToken else { return }
                        playbackStatus = "Playback failed: \(error.localizedDescription)"
                        append(playbackStatus)
                    }
                }
            }
        case .disconnected(let reason):
            isConnected = false
            serverState = "disconnected"
            append("Socket disconnected: \(reason)")
        case .failed(let message):
            append("Socket error: \(message)")
        }
    }

    private func handleServerFrame(_ frame: ServerFrame) {
        guard isSessionRunning else { return }
        switch frame.event {
        case "transcript":
            transcript = frame.text ?? ""
            append("Transcript: \(transcript)")
        case "assistant_text":
            assistantText = frame.text ?? ""
            append("Assistant: \(assistantText)")
        case "active_state":
            serverState = frame.state ?? "unknown"
            append("Server state: \(serverState)")
        case "turn_started":
            serverState = "thinking"
            append("Server: \(frame.event)")
        case "turn_completed", "turn_end":
            if frame.event == "turn_end" {
                serverState = "idle"
                onConversationUpdated()
                if let turnID = frame.turnID {
                    canceledTurnIDs.remove(turnID)
                    if activeAssistantTurnID == turnID {
                        activeAssistantTurnID = nil
                    }
                }
            }
            append("Server: \(frame.event)")
        case "audio_chunk", "voice_turn_skipped", "pong":
            append("Server: \(frame.event)")
        case "error":
            let code = frame.error?.code ?? "unknown"
            let message = frame.error?.message ?? "Unknown error"
            serverState = "error"
            append("Server error \(code): \(message)")
        default:
            append("Server: \(frame.event)")
        }
    }

    private func append(_ event: String) {
        events.append(event)
        eventLog = events.suffix(30).joined(separator: "\n")
    }

    private func scheduleBargeInConfirmation() {
        bargeCandidateID += 1
        let candidateID = bargeCandidateID
        let delaySeconds = audioRouteUsesBluetooth ? settings.bluetoothBargeInDelay : settings.speakerBargeInDelay
        let delay = Duration.milliseconds(Int(delaySeconds * 1000))
        bargeCandidateTask?.cancel()
        bargeCandidateTask = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            await MainActor.run {
                guard let self else { return }
                guard self.bargeCandidateID == candidateID else { return }
                guard self.rawIsSpeaking, self.assistantPlaybackActive, !self.bargeInConfirmed else { return }
                self.confirmBargeIn()
            }
        }
    }

    private func checkForLocalPlaybackInterruption(at: TimeInterval) {
        Task { [weak self] in
            guard let self else { return }
            let isPlayingAudio = await audioPlayer.isPlayingAudio()
            await MainActor.run {
                guard self.rawIsSpeaking, isPlayingAudio, !self.bargeInConfirmed else { return }
                self.assistantPlaybackActive = true
                self.append(String(format: "Potential local audio interrupt at %.2fs", at))
                self.scheduleBargeInConfirmation()
            }
        }
    }

    private func confirmBargeIn() {
        bargeInConfirmed = true
        assistantPlaybackActive = false
        playbackGeneration += 1
        isSpeaking = true
        lastEvent = "speaking"
        playbackStatus = "Interrupted assistant audio"
        append("Barge-in confirmed; canceling assistant turn.")

        let turnID = activeAssistantTurnID
        if let turnID {
            canceledTurnIDs.insert(turnID)
        } else {
            append("Interrupt had no active turn id; flushing local audio only.")
        }

        Task {
            await audioPlayer.stop()
            do {
                try await socket.cancelTurn(turnID: turnID)
            } catch {
                await MainActor.run {
                    append("Cancel failed: \(error.localizedDescription)")
                }
            }
        }
    }

    private func markAssistantPlaybackActive(for data: Data, format: String) -> Int {
        assistantPlaybackActive = true
        bargeInConfirmed = false
        playbackGeneration += 1
        let generation = playbackGeneration
        let duration = estimatedPlaybackDuration(data: data, format: format)

        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(Int((duration + 0.25) * 1000)))
            guard !Task.isCancelled else { return }
            await MainActor.run {
                guard let self, self.playbackGeneration == generation else { return }
                self.assistantPlaybackActive = false
                self.activeAssistantTurnID = nil
                if !self.rawIsSpeaking {
                    self.isSpeaking = false
                    self.lastEvent = "silent"
                }
            }
        }
        return generation
    }

    private func estimatedPlaybackDuration(data: Data, format: String) -> TimeInterval {
        guard format == "wav_pcm16", downlinkSampleRate > 0, downlinkChannels > 0 else {
            return 0.5
        }
        let bytesPerFrame = max(1, downlinkChannels * 2)
        return TimeInterval(data.count / bytesPerFrame) / TimeInterval(downlinkSampleRate)
    }

    private func updateAudioRoute(shouldLog: Bool) {
        let route = audioSession.currentRoute
        let outputs = route.outputs
        audioRouteUsesBluetooth = outputs.contains { output in
            output.portType == .bluetoothA2DP ||
                output.portType == .bluetoothHFP ||
                output.portType == .bluetoothLE
        }

        let routeName = outputs.map(\.portName).joined(separator: ", ")
        let suffix = routeName.isEmpty ? "unknown" : routeName
        audioRouteStatus = audioRouteUsesBluetooth ? "Route: Bluetooth" : "Route: \(suffix)"

        if shouldLog {
            append("\(audioRouteStatus); barge-in \(audioRouteUsesBluetooth ? "easy" : "speaker-safe")")
        }
    }
}

struct VADTestView: View {
    @StateObject private var viewModel: VADTestViewModel
    let config: AppConfig
    let settings: VoiceTuningSettings
    let sessionID: String?
    let historyMessages: [VoiceMessageRecord]
    @Binding private var shouldRun: Bool
    @Binding private var sessionShouldRun: Bool

    init(
        config: AppConfig,
        settings: VoiceTuningSettings,
        sessionID: String?,
        historyMessages: [VoiceMessageRecord],
        shouldRun: Binding<Bool> = .constant(false),
        sessionShouldRun: Binding<Bool> = .constant(false),
        onSessionStarted: @escaping (ServerFrame) -> Void = { _ in },
        onConversationUpdated: @escaping () -> Void = {}
    ) {
        self.config = config
        self.settings = settings
        self.sessionID = sessionID
        self.historyMessages = historyMessages
        _shouldRun = shouldRun
        _sessionShouldRun = sessionShouldRun
        _viewModel = StateObject(wrappedValue: VADTestViewModel(
            config: config,
            settings: settings,
            sessionID: sessionID,
            historyMessages: historyMessages,
            onSessionStarted: onSessionStarted,
            onConversationUpdated: onConversationUpdated
        ))
    }

    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 14) {
                diagnosticsView
                    .frame(maxHeight: max(geometry.size.height * 0.34, 180))

                conversationView
                    .frame(minHeight: geometry.size.height * 0.45, maxHeight: .infinity)

                HStack(spacing: 12) {
                    Button {
                        shouldRun.toggle()
                    } label: {
                        Text(viewModel.isRunning ? "Voice Stop" : "Voice Start")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button {
                        sessionShouldRun.toggle()
                    } label: {
                        Text(viewModel.isSessionRunning ? "Session Stop" : "Session Start")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
            }
            .padding()
        }
        .onChange(of: settings) { _, newSettings in
            viewModel.updateSettings(newSettings)
        }
        .onChange(of: historyMessages) { _, newMessages in
            viewModel.updateHistoryMessages(newMessages)
        }
        .onChange(of: shouldRun) { _, newValue in
            applyVoiceIntent(newValue)
        }
        .onChange(of: sessionShouldRun) { _, newValue in
            applySessionIntent(newValue)
        }
        .onAppear {
            applySessionIntent(sessionShouldRun || shouldRun)
            applyVoiceIntent(shouldRun)
        }
        .onDisappear {
            viewModel.shutdownForSessionSwitch()
        }
    }

    private func applyVoiceIntent(_ shouldRun: Bool) {
        if shouldRun {
            if !sessionShouldRun {
                sessionShouldRun = true
            }
            viewModel.startVoice()
        } else {
            viewModel.stopVoice()
        }
    }

    private func applySessionIntent(_ shouldRun: Bool) {
        if shouldRun {
            viewModel.startSession()
        } else {
            self.shouldRun = false
            viewModel.stopSession()
        }
    }

    private var diagnosticsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Circle()
                        .fill(viewModel.isSpeaking ? Color.green : Color.secondary.opacity(0.35))
                        .frame(width: 18, height: 18)
                        .overlay {
                            Circle()
                                .stroke(viewModel.isRunning ? Color.blue : Color.secondary.opacity(0.4), lineWidth: 2)
                        }
                    Text(viewModel.isSpeaking ? "SPEAKING" : "SILENT")
                        .font(.headline.monospaced().weight(.semibold))
                        .foregroundStyle(viewModel.isSpeaking ? .green : .secondary)
                    Text(viewModel.isRunning ? "VAD running" : "VAD stopped")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                diagnosticRow(
                    title: "Voice",
                    value: viewModel.isRunning ? "listening" : "not listening",
                    color: viewModel.isRunning ? .green : .secondary
                )
                diagnosticRow(
                    title: "Session",
                    value: viewModel.isSessionRunning ? "running" : "stopped",
                    color: viewModel.isSessionRunning ? .green : .secondary
                )
                diagnosticRow(
                    title: "Socket",
                    value: viewModel.isConnected ? "connected" : "disconnected",
                    color: viewModel.isConnected ? .green : .secondary
                )
                diagnosticRow(title: "Server", value: viewModel.serverState)
                diagnosticRow(title: "Route", value: viewModel.audioRouteStatus.replacingOccurrences(of: "Route: ", with: ""))
                if let sessionID {
                    diagnosticRow(title: "Session ID", value: sessionID, isSelectable: true)
                }
                diagnosticRow(title: "Backend", value: config.baseURL.absoluteString, isSelectable: true)
                diagnosticRow(title: "WebSocket", value: config.voiceWebSocketURL.absoluteString, isSelectable: true)

                if !viewModel.downlinkFormat.isEmpty {
                    diagnosticRow(title: "Downlink", value: viewModel.downlinkFormat)
                }
                if !viewModel.playbackStatus.isEmpty {
                    diagnosticRow(title: "Playback", value: viewModel.playbackStatus)
                }
                diagnosticRow(
                    title: "Tuning",
                    value: String(format: "pause %.2fs, speaker barge %.2fs, Bluetooth barge %.2fs",
                                  viewModel.settings.minSilenceDuration,
                                  viewModel.settings.speakerBargeInDelay,
                                  viewModel.settings.bluetoothBargeInDelay)
                )
                if let refusalReason = config.refusalReason {
                    diagnosticRow(title: "Config", value: refusalReason, color: .red)
                }

                Text(viewModel.eventLog)
                    .font(.footnote.monospaced())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                    .padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var conversationView: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Conversation")
                .font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if viewModel.historyMessages.isEmpty && viewModel.transcript.isEmpty && viewModel.assistantText.isEmpty {
                        Text("Transcript and assistant responses will appear here.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    ForEach(viewModel.historyMessages) { message in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(message.role == "assistant" ? "Assistant" : "You")
                                .font(.subheadline.weight(.semibold))
                            Text(message.text)
                                .font(.body)
                                .textSelection(.enabled)
                        }
                    }
                    if !viewModel.transcript.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Transcript")
                                .font(.subheadline.weight(.semibold))
                            Text(viewModel.transcript)
                                .font(.body)
                                .textSelection(.enabled)
                        }
                    }
                    if !viewModel.assistantText.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Assistant")
                                .font(.subheadline.weight(.semibold))
                            Text(viewModel.assistantText)
                                .font(.body)
                                .textSelection(.enabled)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func diagnosticRow(
        title: String,
        value: String,
        color: Color = .secondary,
        isSelectable: Bool = false
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
            if isSelectable {
                Text(value)
                    .font(.footnote.monospaced())
                    .foregroundStyle(color)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            } else {
                Text(value)
                    .font(.footnote.monospaced())
                    .foregroundStyle(color)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
