import AVFoundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "AudioPlayback")

/// Streams server-side TTS audio (wav_pcm16 chunks) to the speaker.
///
/// The server sends raw int16 LE PCM at 24 kHz (OpenAI "pcm" format, no header).
/// AVAudioPlayerNode requires float32, so each chunk is converted on arrival.
@MainActor
final class AudioPlayback {

    private let engine = AVAudioEngine()
    private let playerNode = AVAudioPlayerNode()
    private(set) var currentTurnID: String?

    // Float32 non-interleaved — the only format AVAudioPlayerNode accepts.
    private var playFormat: AVAudioFormat

    init(sampleRate: Double = 24_000) {
        playFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        )!
        engine.attach(playerNode)
        engine.connect(playerNode, to: engine.mainMixerNode, format: playFormat)
    }

    // MARK: - Session negotiation

    /// Call when session_started arrives to match the server's sample rate.
    func configure(sampleRate: Double) {
        guard sampleRate != playFormat.sampleRate else { return }
        playFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        )!
        engine.disconnectNodeOutput(playerNode)
        engine.connect(playerNode, to: engine.mainMixerNode, format: playFormat)
        log.info("AudioPlayback reconfigured: \(sampleRate, privacy: .public) Hz")
    }

    // MARK: - Streaming

    /// Schedule one raw PCM16 chunk for playback. Chunks from the same turn
    /// queue seamlessly; a chunk from a new turn stops current playback first.
    func scheduleChunk(_ data: Data, turnID: String) {
        guard !data.isEmpty else { return }

        if let current = currentTurnID, current != turnID {
            playerNode.stop()
            log.debug("New turn \(turnID) — stopped previous playback")
        }
        currentTurnID = turnID

        startEngineIfNeeded()

        // Server sends raw int16 LE (no WAV header). Convert to float32 for AVAudioPlayerNode.
        let frameCount = AVAudioFrameCount(data.count / 2)
        guard frameCount > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: playFormat, frameCapacity: frameCount)
        else { return }

        buffer.frameLength = frameCount
        let scale = Float(1.0 / Float(Int16.max))
        data.withUnsafeBytes { raw in
            guard let src = raw.bindMemory(to: Int16.self).baseAddress,
                  let dst = buffer.floatChannelData else { return }
            for i in 0..<Int(frameCount) {
                dst[0][i] = Float(src[i]) * scale
            }
        }

        if !playerNode.isPlaying { playerNode.play() }
        playerNode.scheduleBuffer(buffer)
        log.debug("Scheduled \(frameCount) frames for turn \(turnID)")
    }

    /// Immediately stops playback and resets the player node so no samples
    /// from the cancelled turn can bleed into the next one.
    func cancelCurrentTurn() {
        currentTurnID = nil
        playerNode.stop()
        playerNode.reset()
        log.debug("AudioPlayback cancelled")
    }

    // MARK: - Private

    private func startEngineIfNeeded() {
        guard !engine.isRunning else { return }
        do {
            try AudioSessionManager.configureForVoice()
            try engine.start()
            log.info("AudioPlayback engine started")
        } catch {
            log.error("AudioPlayback engine failed to start: \(error)")
        }
    }
}
