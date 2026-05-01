import AVFoundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "HandsFreeCapture")

private let kTargetSampleRate: Double = 16_000
private let kTargetChannels: AVAudioChannelCount = 1

/// Keeps AVAudioEngine running continuously for hands-free mode.
///
/// Unlike AudioCapture (which starts/stops the engine per utterance), this
/// class runs the engine the whole time. Call beginUtterance() / endUtterance()
/// to delimit individual turns within the continuous stream.
///
/// Fires onAudioLevel on the main thread with the RMS of each ~85 ms chunk
/// so VoiceActivityDetector can react without any extra dispatching.
final class HandsFreeCapture {

    private(set) var isRunning = false
    private(set) var isCapturingUtterance = false

    /// RMS energy (0–1) of each incoming audio chunk — main thread.
    var onAudioLevel: ((Float) -> Void)?

    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var pcmChunks: [Data] = []
    private let pcmLock = NSLock()

    // MARK: - Engine lifecycle

    func start() throws {
        guard !isRunning else { return }

        let inputNode = engine.inputNode
        let nativeFormat = inputNode.outputFormat(forBus: 0)

        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: kTargetSampleRate,
            channels: kTargetChannels,
            interleaved: true
        ) else { throw CaptureError.formatUnavailable }

        guard let conv = AVAudioConverter(from: nativeFormat, to: targetFormat) else {
            throw CaptureError.converterUnavailable
        }
        converter = conv

        let ratio = kTargetSampleRate / nativeFormat.sampleRate
        inputNode.installTap(onBus: 0, bufferSize: 4096, format: nativeFormat) { [weak self] inBuf, _ in
            guard let self else { return }

            // Compute RMS for VAD — done on audio thread, dispatched to main.
            let rms = Self.rms(buffer: inBuf)
            DispatchQueue.main.async { self.onAudioLevel?(rms) }

            // Resample to 16 kHz int16 mono.
            let outFrames = AVAudioFrameCount(ceil(Double(inBuf.frameLength) * ratio))
            guard outFrames > 0,
                  let outBuf = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outFrames)
            else { return }

            var inputProvided = false
            conv.convert(to: outBuf, error: nil) { _, outStatus in
                if inputProvided { outStatus.pointee = .noDataNow; return nil }
                inputProvided = true
                outStatus.pointee = .haveData
                return inBuf
            }

            guard outBuf.frameLength > 0, let ch = outBuf.int16ChannelData else { return }
            let bytes = Data(bytes: ch[0], count: Int(outBuf.frameLength) * 2)

            self.pcmLock.lock()
            if self.isCapturingUtterance { self.pcmChunks.append(bytes) }
            self.pcmLock.unlock()
        }

        try engine.start()
        isRunning = true
        log.info("HandsFreeCapture started: \(nativeFormat.sampleRate, privacy: .public) Hz → 16000 Hz")
    }

    func stop() {
        guard isRunning else { return }
        isRunning = false
        isCapturingUtterance = false
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
        pcmLock.lock(); pcmChunks.removeAll(); pcmLock.unlock()
        log.info("HandsFreeCapture stopped")
    }

    // MARK: - Utterance delimiting

    func beginUtterance() {
        guard isRunning, !isCapturingUtterance else { return }
        pcmLock.lock(); pcmChunks.removeAll(); pcmLock.unlock()
        isCapturingUtterance = true
        log.debug("HandsFreeCapture: utterance begun")
    }

    /// Stops accumulating and returns a WAV-wrapped payload, or nil if nothing recorded.
    func endUtterance() -> Data? {
        guard isCapturingUtterance else { return nil }
        isCapturingUtterance = false

        pcmLock.lock()
        let chunks = pcmChunks
        pcmChunks.removeAll()
        pcmLock.unlock()

        guard !chunks.isEmpty else { return nil }
        let pcm = chunks.reduce(Data(), +)
        log.info("HandsFreeCapture: utterance ended — \(pcm.count) PCM bytes → WAV")
        return makeWAV(pcm: pcm)
    }

    // MARK: - Helpers

    private static func rms(buffer: AVAudioPCMBuffer) -> Float {
        guard let data = buffer.floatChannelData else { return 0 }
        let frameCount = Int(buffer.frameLength)
        guard frameCount > 0 else { return 0 }
        var sum: Float = 0
        for i in 0..<frameCount { sum += data[0][i] * data[0][i] }
        return (sum / Float(frameCount)).squareRoot()
    }

    private func makeWAV(pcm: Data) -> Data {
        let sampleRate = Int32(kTargetSampleRate)
        let channels: Int16 = Int16(kTargetChannels)
        let bitsPerSample: Int16 = 16
        let dataSize = Int32(pcm.count)
        let byteRate = sampleRate * Int32(channels) * Int32(bitsPerSample / 8)
        let blockAlign = channels * (bitsPerSample / 8)

        var h = Data(); h.reserveCapacity(44 + pcm.count)
        func le<T: FixedWidthInteger>(_ v: T) {
            withUnsafeBytes(of: v.littleEndian) { h.append(contentsOf: $0) }
        }
        h += "RIFF".data(using: .ascii)!; le(Int32(36 + dataSize))
        h += "WAVE".data(using: .ascii)!
        h += "fmt ".data(using: .ascii)!; le(Int32(16)); le(Int16(1))
        le(channels); le(sampleRate); le(byteRate); le(blockAlign); le(bitsPerSample)
        h += "data".data(using: .ascii)!; le(dataSize)
        return h + pcm
    }
}
