import AVFoundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "AudioPlayback")

/// Streams server-side TTS audio (wav_pcm16 chunks) to the speaker.
///
/// Chunks arrive as raw int16 LE PCM bytes. Each chunk is wrapped in an
/// AVAudioPCMBuffer and scheduled on the player node, so playback is
/// continuous without gaps between chunks.
@MainActor
final class AudioPlayback {

    private let engine = AVAudioEngine()
    private let playerNode = AVAudioPlayerNode()
    private(set) var currentTurnID: String?

    // Fixed at the negotiated format; reconfigured on session_started if needed.
    private var pcmFormat: AVAudioFormat

    init(sampleRate: Double = 16_000) {
        pcmFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: true
        )!
        engine.attach(playerNode)
        engine.connect(playerNode, to: engine.mainMixerNode, format: pcmFormat)
    }

    // MARK: - Session negotiation

    /// Call when session_started arrives to match the server's sample rate.
    func configure(sampleRate: Double) {
        guard sampleRate != pcmFormat.sampleRate else { return }
        pcmFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: true
        )!
        engine.disconnectNodeOutput(playerNode)
        engine.connect(playerNode, to: engine.mainMixerNode, format: pcmFormat)
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

        let frameCount = AVAudioFrameCount(data.count / 2)  // 2 bytes per int16 sample
        guard frameCount > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: pcmFormat, frameCapacity: frameCount)
        else { return }

        buffer.frameLength = frameCount
        data.withUnsafeBytes { raw in
            guard let src = raw.bindMemory(to: Int16.self).baseAddress,
                  let dst = buffer.int16ChannelData else { return }
            dst[0].assign(from: src, count: Int(frameCount))
        }

        if !playerNode.isPlaying { playerNode.play() }
        playerNode.scheduleBuffer(buffer)
        log.debug("Scheduled \(frameCount) frames for turn \(turnID) seq chunk")
    }

    /// Immediately stops playback (called on cancel_turn or new PTT press).
    func cancelCurrentTurn() {
        currentTurnID = nil
        playerNode.stop()
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
