import AVFoundation
import Foundation
import os

actor AudioPlayer {
    private let logger = Logger(subsystem: "com.dashanddata.HermesVoice", category: "audio-player")
    private let engine = AVAudioEngine()
    private let playerNode = AVAudioPlayerNode()

    private var isPrepared = false
    private var scheduledBuffers = 0

    func play(audio data: Data, format: String, sampleRate: Int, channels: Int) async throws {
        guard !data.isEmpty else {
            return
        }

        switch format {
        case "wav_pcm16":
            try playPCM16(data, sampleRate: sampleRate, channels: channels)
        default:
            throw AudioPlayerError.unsupportedFormat(format)
        }
    }

    func stop() {
        playerNode.stop()
        playerNode.reset()
        scheduledBuffers = 0
    }

    private func prepareIfNeeded(sampleRate: Int, channels: Int) throws -> AVAudioFormat {
        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: Double(sampleRate),
            channels: AVAudioChannelCount(channels),
            interleaved: false
        ) else {
            throw AudioPlayerError.invalidFormat
        }

        if !isPrepared {
            engine.attach(playerNode)
            engine.connect(playerNode, to: engine.mainMixerNode, format: format)
            isPrepared = true
        }

        if !engine.isRunning {
            try engine.start()
        }

        if !playerNode.isPlaying {
            playerNode.play()
        }

        return format
    }

    private func playPCM16(_ data: Data, sampleRate: Int, channels: Int) throws {
        guard channels == 1 else {
            throw AudioPlayerError.unsupportedChannelCount(channels)
        }
        guard data.count >= 2, data.count % 2 == 0 else {
            throw AudioPlayerError.invalidPCMData
        }

        let format = try prepareIfNeeded(sampleRate: sampleRate, channels: channels)
        let frameCount = AVAudioFrameCount(data.count / 2)
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else {
            throw AudioPlayerError.invalidFormat
        }

        buffer.frameLength = frameCount
        guard let channel = buffer.floatChannelData?[0] else {
            throw AudioPlayerError.invalidFormat
        }

        data.withUnsafeBytes { rawBuffer in
            let int16Buffer = rawBuffer.bindMemory(to: Int16.self)
            for index in 0 ..< int16Buffer.count {
                channel[index] = Float(Int16(littleEndian: int16Buffer[index])) / Float(Int16.max)
            }
        }

        scheduledBuffers += 1
        let bufferNumber = scheduledBuffers
        playerNode.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [logger] _ in
            logger.info("Played PCM16 buffer \(bufferNumber, privacy: .public)")
        }
        logger.info("Scheduled PCM16 audio: \(data.count, privacy: .public) bytes")
    }
}

enum AudioPlayerError: LocalizedError {
    case unsupportedFormat(String)
    case unsupportedChannelCount(Int)
    case invalidFormat
    case invalidPCMData

    var errorDescription: String? {
        switch self {
        case .unsupportedFormat(let format):
            return "Unsupported audio format: \(format)."
        case .unsupportedChannelCount(let channels):
            return "Unsupported channel count: \(channels)."
        case .invalidFormat:
            return "Could not create an audio playback format."
        case .invalidPCMData:
            return "Received invalid PCM audio data."
        }
    }
}
