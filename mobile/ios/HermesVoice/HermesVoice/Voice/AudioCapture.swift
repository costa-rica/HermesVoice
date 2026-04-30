import AVFoundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "AudioCapture")

// Uplink spec (V04/V06, unchanged): 16 kHz, 16-bit signed LE, mono, WAV container.
private let kTargetSampleRate: Double = 16_000
private let kTargetChannels: AVAudioChannelCount = 1

final class AudioCapture {

    private(set) var isRecording = false

    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var pcmChunks: [Data] = []
    private let pcmLock = NSLock()

    // MARK: - Start

    /// Installs a tap on the input node, resamples to 16 kHz int16 mono in real-time,
    /// and starts the engine. Throws if the session or engine fails to start.
    func startCapture() throws {
        guard !isRecording else { return }
        pcmChunks.removeAll()

        let inputNode = engine.inputNode
        let nativeFormat = inputNode.outputFormat(forBus: 0)

        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: kTargetSampleRate,
            channels: kTargetChannels,
            interleaved: true
        ) else {
            throw CaptureError.formatUnavailable
        }

        guard let conv = AVAudioConverter(from: nativeFormat, to: targetFormat) else {
            throw CaptureError.converterUnavailable
        }
        converter = conv

        let ratio = kTargetSampleRate / nativeFormat.sampleRate
        inputNode.installTap(onBus: 0, bufferSize: 4096, format: nativeFormat) { [weak self] inBuf, _ in
            guard let self else { return }
            let outFrames = AVAudioFrameCount(ceil(Double(inBuf.frameLength) * ratio))
            guard outFrames > 0,
                  let outBuf = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outFrames)
            else { return }

            // Feed exactly one input buffer per convert call (standard real-time pattern).
            var inputProvided = false
            conv.convert(to: outBuf, error: nil) { _, outStatus in
                if inputProvided {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                inputProvided = true
                outStatus.pointee = .haveData
                return inBuf
            }

            guard outBuf.frameLength > 0, let ch = outBuf.int16ChannelData else { return }
            let bytes = Data(bytes: ch[0], count: Int(outBuf.frameLength) * 2)

            self.pcmLock.lock()
            self.pcmChunks.append(bytes)
            self.pcmLock.unlock()
        }

        try engine.start()
        isRecording = true
        log.info("AudioCapture started: hardware=\(nativeFormat.sampleRate, privacy: .public) Hz → 16000 Hz int16 mono")
    }

    // MARK: - Stop

    /// Stops the engine, collects accumulated PCM, and returns a WAV-wrapped payload.
    /// Returns nil if nothing was recorded.
    func stopCapture() -> Data? {
        guard isRecording else { return nil }
        isRecording = false

        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil

        pcmLock.lock()
        let chunks = pcmChunks
        pcmChunks.removeAll()
        pcmLock.unlock()

        guard !chunks.isEmpty else {
            log.debug("AudioCapture stopped — no audio captured")
            return nil
        }

        let pcm = chunks.reduce(Data(), +)
        log.info("AudioCapture stopped — \(pcm.count) PCM bytes → WAV")
        return makeWAV(pcm: pcm)
    }

    // MARK: - WAV builder

    /// Wraps raw int16 LE mono PCM at 16 kHz in a minimal RIFF WAV container.
    private func makeWAV(pcm: Data) -> Data {
        let sampleRate: Int32 = Int32(kTargetSampleRate)
        let channels: Int16 = Int16(kTargetChannels)
        let bitsPerSample: Int16 = 16
        let dataSize = Int32(pcm.count)
        let byteRate = sampleRate * Int32(channels) * Int32(bitsPerSample / 8)
        let blockAlign = channels * (bitsPerSample / 8)

        var h = Data()
        h.reserveCapacity(44 + pcm.count)

        func le<T: FixedWidthInteger>(_ v: T) {
            withUnsafeBytes(of: v.littleEndian) { h.append(contentsOf: $0) }
        }

        h += "RIFF".ascii
        le(Int32(36 + dataSize))  // file size − 8
        h += "WAVE".ascii
        h += "fmt ".ascii
        le(Int32(16))             // PCM fmt chunk size
        le(Int16(1))              // PCM audio format
        le(channels)
        le(sampleRate)
        le(byteRate)
        le(blockAlign)
        le(bitsPerSample)
        h += "data".ascii
        le(dataSize)

        return h + pcm
    }
}

// MARK: - Errors

enum CaptureError: LocalizedError {
    case formatUnavailable
    case converterUnavailable
    case permissionDenied

    var errorDescription: String? {
        switch self {
        case .formatUnavailable:   return "Audio format unavailable."
        case .converterUnavailable: return "Audio converter unavailable."
        case .permissionDenied:    return "Microphone access is required. Enable it in Settings."
        }
    }
}

// MARK: - Private helper

private extension String {
    var ascii: Data { data(using: .ascii)! }
}
