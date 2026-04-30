import Foundation

// MARK: - Downlink format

enum DownlinkFormat: String, Codable, Sendable {
    case aacAdts = "aac_adts"
    case wavPCM16 = "wav_pcm16"
    case opusOgg = "opus_ogg"
}

// MARK: - Active state (mirrors backend active_state values 1:1)

enum ActiveState: String, Codable, Sendable {
    case idle
    case listening
    case thinking
    case thinkingProgress = "thinking_progress"
    case speaking
    case awaitingApproval = "awaiting_approval"
}

// MARK: - Inbound frame payloads (server → client)

struct SessionStartedFrame: Decodable, Sendable {
    let conversationID: String
    let downlinkFormat: DownlinkFormat
    let downlinkSampleRate: Int
    let downlinkChannels: Int

    enum CodingKeys: String, CodingKey {
        case conversationID = "conversation_id"
        case downlinkFormat = "downlink_format"
        case downlinkSampleRate = "downlink_sample_rate"
        case downlinkChannels = "downlink_channels"
    }
}

struct TurnStartedFrame: Decodable, Sendable {
    let turnID: String
    enum CodingKeys: String, CodingKey { case turnID = "turn_id" }
}

struct TranscriptFrame: Decodable, Sendable {
    let text: String
    let turnID: String
    enum CodingKeys: String, CodingKey {
        case text
        case turnID = "turn_id"
    }
}

struct ActiveStateFrame: Decodable, Sendable {
    let state: ActiveState
    // turn_id is absent for session-level idle
    let turnID: String?
    enum CodingKeys: String, CodingKey {
        case state
        case turnID = "turn_id"
    }
}

/// JSON prelude that immediately precedes each binary audio WebSocket frame (Option A).
struct AudioChunkFrame: Decodable, Sendable {
    let turnID: String
    let seq: Int
    let format: String
    let bytes: Int
    enum CodingKeys: String, CodingKey {
        case turnID = "turn_id"
        case seq, format, bytes
    }
}

struct AssistantTextFrame: Decodable, Sendable {
    let text: String
    let isFinal: Bool
    let turnID: String
    enum CodingKeys: String, CodingKey {
        case text
        case isFinal = "final"
        case turnID = "turn_id"
    }
}

struct TurnCompletedFrame: Decodable, Sendable {
    let turnID: String
    enum CodingKeys: String, CodingKey { case turnID = "turn_id" }
}

struct TurnEndFrame: Decodable, Sendable {
    // turn_id may be absent when the turn was cancelled before it got an ID
    let turnID: String?
    enum CodingKeys: String, CodingKey { case turnID = "turn_id" }
}

struct VoiceTurnSkippedFrame: Decodable, Sendable {
    let reason: String
    let turnID: String
    enum CodingKeys: String, CodingKey {
        case reason
        case turnID = "turn_id"
    }
}

struct PongFrame: Decodable, Sendable {
    let id: String?
}

struct ErrorPayload: Decodable, Sendable {
    let code: String
    let message: String
    let status: Int
}

struct ServerErrorFrame: Decodable, Sendable {
    let error: ErrorPayload
}

// MARK: - Inbound discriminated union

enum InboundFrame: Sendable {
    case sessionStarted(SessionStartedFrame)
    case turnStarted(TurnStartedFrame)
    case transcript(TranscriptFrame)
    case activeState(ActiveStateFrame)
    case audioChunk(AudioChunkFrame)
    case assistantText(AssistantTextFrame)
    case turnCompleted(TurnCompletedFrame)
    case turnEnd(TurnEndFrame)
    case voiceTurnSkipped(VoiceTurnSkippedFrame)
    case pong(PongFrame)
    case error(ServerErrorFrame)
    /// Unknown event: logged, never crashed on.
    case unknown(String)
}

extension InboundFrame {
    static func decode(from text: String) -> InboundFrame {
        guard let data = text.data(using: .utf8),
              let disc = try? JSONDecoder().decode(EventDiscriminator.self, from: data)
        else { return .unknown(text) }

        let d = JSONDecoder()
        switch disc.event {
        case "session_started":
            if let f = try? d.decode(SessionStartedFrame.self, from: data) { return .sessionStarted(f) }
        case "turn_started":
            if let f = try? d.decode(TurnStartedFrame.self, from: data) { return .turnStarted(f) }
        case "transcript":
            if let f = try? d.decode(TranscriptFrame.self, from: data) { return .transcript(f) }
        case "active_state":
            if let f = try? d.decode(ActiveStateFrame.self, from: data) { return .activeState(f) }
        case "audio_chunk":
            if let f = try? d.decode(AudioChunkFrame.self, from: data) { return .audioChunk(f) }
        case "assistant_text":
            if let f = try? d.decode(AssistantTextFrame.self, from: data) { return .assistantText(f) }
        case "turn_completed":
            if let f = try? d.decode(TurnCompletedFrame.self, from: data) { return .turnCompleted(f) }
        case "turn_end":
            if let f = try? d.decode(TurnEndFrame.self, from: data) { return .turnEnd(f) }
        case "voice_turn_skipped":
            if let f = try? d.decode(VoiceTurnSkippedFrame.self, from: data) { return .voiceTurnSkipped(f) }
        case "pong":
            if let f = try? d.decode(PongFrame.self, from: data) { return .pong(f) }
        case "error":
            if let f = try? d.decode(ServerErrorFrame.self, from: data) { return .error(f) }
        default: break
        }
        return .unknown(text)
    }
}

private struct EventDiscriminator: Decodable {
    let event: String
}

// MARK: - Outbound frame types (client → server)

struct ClientHelloFrame: Encodable {
    let event = "client_hello"
    let acceptedDownlinkFormats: [String]
    enum CodingKeys: String, CodingKey {
        case event
        case acceptedDownlinkFormats = "accepted_downlink_formats"
    }
}

struct StartUtteranceFrame: Encodable {
    let event = "start_utterance"
    let format: String
    let sampleRate: Int
    enum CodingKeys: String, CodingKey {
        case event, format
        case sampleRate = "sample_rate"
    }
}

struct EndOfUtteranceFrame: Encodable {
    let event = "end_of_utterance"
}

struct CancelTurnOutbound: Encodable {
    let event = "cancel_turn"
    let turnID: String?
    enum CodingKeys: String, CodingKey {
        case event
        case turnID = "turn_id"
    }
}

struct PingOutbound: Encodable {
    let event = "ping"
    let id: String?
}
