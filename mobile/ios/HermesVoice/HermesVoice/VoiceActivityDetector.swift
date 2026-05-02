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

    private var audioEngine: AVAudioEngine?
    private var audioSession = AVAudioSession.sharedInstance()
    private var vadModelConfig: SherpaOnnxVadModelConfig?
    private var vad: SherpaOnnxVoiceActivityDetectorWrapper?
    private var pendingSamples: [Float] = []
    private var processedSamples = 0
    private var speechStartSamples: Int?
    private var continuation: AsyncStream<VADEvent>.Continuation?

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
            minSilenceDuration: 0.35,
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
                mode: .measurement,
                options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers]
            )
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
    @Published var isSpeaking = false
    @Published var isConnected = false
    @Published var lastEvent = "silent"
    @Published var eventLog = "Ready. Press Start and allow microphone access."
    @Published var transcript = ""
    @Published var assistantText = ""
    @Published var downlinkFormat = ""
    @Published var serverState = "idle"
    @Published var playbackStatus = ""

    private let detector = VoiceActivityDetector()
    private let socket: VoiceSocket
    private let audioPlayer = AudioPlayer()
    private var eventTask: Task<Void, Never>?
    private var socketTask: Task<Void, Never>?
    private var events: [String] = []
    private var downlinkSampleRate = 16000
    private var downlinkChannels = 1

    init(config: AppConfig) {
        socket = VoiceSocket(config: config)
    }

    func start() {
        guard !isRunning else { return }
        isRunning = true
        events.removeAll()
        eventLog = "Starting..."
        transcript = ""
        assistantText = ""
        serverState = "idle"
        playbackStatus = ""

        socketTask = Task {
            let stream = await socket.events()
            Task {
                await socket.connect()
            }

            for await event in stream {
                handleSocket(event)
            }
        }

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

    func stop() {
        guard isRunning else { return }
        Task {
            await detector.stop()
            await MainActor.run {
                isRunning = false
                isSpeaking = false
                lastEvent = "silent"
            }
        }
        eventTask?.cancel()
        eventTask = nil
        socketTask?.cancel()
        socketTask = nil
        Task {
            await audioPlayer.stop()
            await socket.disconnect(reason: "stopped")
        }
    }

    private func handle(_ event: VADEvent) {
        switch event {
        case .started(let at):
            append(String(format: "Speech start at %.2fs", at))
        case .ended(let at, let duration, let samples):
            append(String(format: "Speech end at %.2fs, duration %.2fs", at, duration))
            Task {
                do {
                    try await socket.sendUtterance(samples: samples)
                    await MainActor.run {
                        append(String(format: "Sent utterance: %.2fs", duration))
                    }
                } catch {
                    await MainActor.run {
                        append("Utterance send failed: \(error.localizedDescription)")
                    }
                }
            }
        case .stateChanged(let speaking):
            isSpeaking = speaking
            lastEvent = speaking ? "speaking" : "silent"
        case .message(let message):
            append(message)
        }
    }

    private func handleSocket(_ event: VoiceSocketEvent) {
        switch event {
        case .connected(let frame):
            isConnected = true
            downlinkFormat = frame.downlinkFormat ?? ""
            downlinkSampleRate = frame.downlinkSampleRate ?? 16000
            downlinkChannels = frame.downlinkChannels ?? 1
            append("Socket connected: \(downlinkFormat)")
        case .frame(let frame):
            handleServerFrame(frame)
        case .audioChunk(let data, let prelude):
            let format = prelude.format ?? downlinkFormat
            append("Audio chunk \(prelude.seq ?? 0): \(data.count) bytes \(format)")
            playbackStatus = "Playing \(format) \(data.count) bytes"
            Task {
                do {
                    try await audioPlayer.play(
                        audio: data,
                        format: format,
                        sampleRate: downlinkSampleRate,
                        channels: downlinkChannels
                    )
                    await MainActor.run {
                        playbackStatus = "Queued audio: \(data.count) bytes"
                    }
                } catch {
                    await MainActor.run {
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
}

struct VADTestView: View {
    @StateObject private var viewModel: VADTestViewModel
    let config: AppConfig

    init(config: AppConfig) {
        self.config = config
        _viewModel = StateObject(wrappedValue: VADTestViewModel(config: config))
    }

    var body: some View {
        VStack(spacing: 18) {
            VStack(spacing: 10) {
                Circle()
                    .fill(viewModel.isSpeaking ? Color.green : Color.secondary.opacity(0.35))
                    .frame(width: 96, height: 96)
                    .overlay {
                        Circle()
                            .stroke(viewModel.isRunning ? Color.blue : Color.secondary.opacity(0.4), lineWidth: 4)
                    }
                Text(viewModel.isSpeaking ? "SPEAKING" : "SILENT")
                    .font(.title2.monospaced().weight(.semibold))
                Text(viewModel.isRunning ? "VAD running" : "VAD stopped")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text(viewModel.isConnected ? "Socket connected" : "Socket disconnected")
                    .font(.caption)
                    .foregroundStyle(viewModel.isConnected ? .green : .secondary)
                Text("Server: \(viewModel.serverState)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 24)

            VStack(alignment: .leading, spacing: 8) {
                Text("Backend")
                    .font(.headline)
                Text(config.baseURL.absoluteString)
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
                Text(config.voiceWebSocketURL.absoluteString)
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
                if !viewModel.downlinkFormat.isEmpty {
                    Text("Downlink: \(viewModel.downlinkFormat)")
                        .font(.footnote.monospaced())
                }
                if !viewModel.playbackStatus.isEmpty {
                    Text(viewModel.playbackStatus)
                        .font(.footnote.monospaced())
                }
                if let refusalReason = config.refusalReason {
                    Text(refusalReason)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if !viewModel.transcript.isEmpty || !viewModel.assistantText.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    if !viewModel.transcript.isEmpty {
                        Text("Transcript")
                            .font(.headline)
                        Text(viewModel.transcript)
                            .font(.body)
                    }
                    if !viewModel.assistantText.isEmpty {
                        Text("Assistant")
                            .font(.headline)
                        Text(viewModel.assistantText)
                            .font(.body)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            ScrollView {
                Text(viewModel.eventLog)
                    .font(.footnote.monospaced())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(maxHeight: .infinity)

            Button {
                viewModel.isRunning ? viewModel.stop() : viewModel.start()
            } label: {
                Text(viewModel.isRunning ? "Stop" : "Start")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding()
    }
}
