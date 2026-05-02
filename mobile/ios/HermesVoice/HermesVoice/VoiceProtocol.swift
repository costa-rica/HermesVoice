import Foundation

struct ClientHelloFrame: Encodable {
    let event = "client_hello"
    let client = "ios"
    let clientVersion = "0.0.1-dev"
    let acceptedDownlinkFormats = ["wav_pcm16", "aac_adts"]

    enum CodingKeys: String, CodingKey {
        case event
        case client
        case clientVersion = "client_version"
        case acceptedDownlinkFormats = "accepted_downlink_formats"
    }
}

struct StartUtteranceFrame: Encodable {
    let event = "start_utterance"
    let format = "wav"
    let sampleRate = 16000

    enum CodingKeys: String, CodingKey {
        case event
        case format
        case sampleRate = "sample_rate"
    }
}

struct EndOfUtteranceFrame: Encodable {
    let event = "end_of_utterance"
}

struct PingFrame: Encodable {
    let event = "ping"
    let id: String
}

struct ServerFrame: Decodable, Equatable {
    let event: String
    let conversationID: String?
    let downlinkFormat: String?
    let downlinkSampleRate: Int?
    let downlinkChannels: Int?
    let turnID: String?
    let state: String?
    let text: String?
    let final: Bool?
    let seq: Int?
    let format: String?
    let bytes: Int?
    let error: ServerErrorFrame?
    let reason: String?
    let id: String?

    enum CodingKeys: String, CodingKey {
        case event
        case conversationID = "conversation_id"
        case downlinkFormat = "downlink_format"
        case downlinkSampleRate = "downlink_sample_rate"
        case downlinkChannels = "downlink_channels"
        case turnID = "turn_id"
        case state
        case text
        case final
        case seq
        case format
        case bytes
        case error
        case reason
        case id
    }
}

struct ServerErrorFrame: Decodable, Equatable {
    let code: String?
    let message: String?
    let status: Int?
    let details: String?
}

enum VoiceSocketEvent: Equatable {
    case connected(ServerFrame)
    case frame(ServerFrame)
    case audioChunk(Data, ServerFrame)
    case disconnected(String)
    case failed(String)
}

enum WavEncoder {
    static func pcm16Wav(samples: [Float], sampleRate: Int = 16000) -> Data {
        var pcm = Data()
        pcm.reserveCapacity(samples.count * MemoryLayout<Int16>.size)

        for sample in samples {
            let clamped = max(-1.0, min(1.0, sample))
            let scaled = Int16(clamped * Float(Int16.max))
            var littleEndian = scaled.littleEndian
            withUnsafeBytes(of: &littleEndian) { pcm.append(contentsOf: $0) }
        }

        var wav = Data()
        wav.appendASCII("RIFF")
        wav.appendUInt32LE(UInt32(36 + pcm.count))
        wav.appendASCII("WAVE")
        wav.appendASCII("fmt ")
        wav.appendUInt32LE(16)
        wav.appendUInt16LE(1)
        wav.appendUInt16LE(1)
        wav.appendUInt32LE(UInt32(sampleRate))
        wav.appendUInt32LE(UInt32(sampleRate * 2))
        wav.appendUInt16LE(2)
        wav.appendUInt16LE(16)
        wav.appendASCII("data")
        wav.appendUInt32LE(UInt32(pcm.count))
        wav.append(pcm)
        return wav
    }
}

private extension Data {
    mutating func appendASCII(_ string: String) {
        append(string.data(using: .ascii)!)
    }

    mutating func appendUInt16LE(_ value: UInt16) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }

    mutating func appendUInt32LE(_ value: UInt32) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }
}
