import XCTest
@testable import HermesVoice

// MARK: - Frame decode round-trip tests

final class InboundFrameDecodeTests: XCTestCase {

    private func json(_ pairs: [String: Any]) -> String {
        let data = try! JSONSerialization.data(withJSONObject: pairs)
        return String(data: data, encoding: .utf8)!
    }

    // MARK: session_started

    func testDecodeSessionStarted() {
        let text = json([
            "event": "session_started",
            "conversation_id": "conv-abc",
            "downlink_format": "aac_adts",
            "downlink_sample_rate": 24000,
            "downlink_channels": 1,
        ])
        guard case .sessionStarted(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .sessionStarted")
        }
        XCTAssertEqual(f.conversationID, "conv-abc")
        XCTAssertEqual(f.downlinkFormat, .aacAdts)
        XCTAssertEqual(f.downlinkSampleRate, 24000)
        XCTAssertEqual(f.downlinkChannels, 1)
    }

    func testDecodeSessionStartedPCMFallback() {
        let text = json([
            "event": "session_started",
            "conversation_id": "c1",
            "downlink_format": "wav_pcm16",
            "downlink_sample_rate": 16000,
            "downlink_channels": 1,
        ])
        guard case .sessionStarted(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .sessionStarted")
        }
        XCTAssertEqual(f.downlinkFormat, .wavPCM16)
        XCTAssertEqual(f.downlinkSampleRate, 16000)
    }

    // MARK: turn_started

    func testDecodeTurnStarted() {
        let text = json(["event": "turn_started", "turn_id": "42"])
        guard case .turnStarted(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .turnStarted")
        }
        XCTAssertEqual(f.turnID, "42")
    }

    // MARK: transcript

    func testDecodeTranscript() {
        let text = json(["event": "transcript", "text": "hello world", "turn_id": "7"])
        guard case .transcript(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .transcript")
        }
        XCTAssertEqual(f.text, "hello world")
        XCTAssertEqual(f.turnID, "7")
    }

    // MARK: active_state (with and without turn_id)

    func testDecodeActiveStateThinking() {
        let text = json(["event": "active_state", "state": "thinking", "turn_id": "3"])
        guard case .activeState(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .activeState")
        }
        XCTAssertEqual(f.state, .thinking)
        XCTAssertEqual(f.turnID, "3")
    }

    func testDecodeActiveStateIdleOmitsTurnID() {
        let text = json(["event": "active_state", "state": "idle"])
        guard case .activeState(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .activeState")
        }
        XCTAssertEqual(f.state, .idle)
        XCTAssertNil(f.turnID)
    }

    func testDecodeActiveStateThinkingProgress() {
        let text = json(["event": "active_state", "state": "thinking_progress", "turn_id": "5"])
        guard case .activeState(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .activeState")
        }
        XCTAssertEqual(f.state, .thinkingProgress)
    }

    func testDecodeActiveStateSpeaking() {
        let text = json(["event": "active_state", "state": "speaking", "turn_id": "9"])
        guard case .activeState(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .activeState")
        }
        XCTAssertEqual(f.state, .speaking)
    }

    // MARK: audio_chunk prelude

    func testDecodeAudioChunk() {
        let text = json([
            "event": "audio_chunk",
            "turn_id": "2",
            "seq": 0,
            "format": "aac_adts",
            "bytes": 4096,
        ])
        guard case .audioChunk(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .audioChunk")
        }
        XCTAssertEqual(f.turnID, "2")
        XCTAssertEqual(f.seq, 0)
        XCTAssertEqual(f.bytes, 4096)
        XCTAssertEqual(f.format, "aac_adts")
    }

    // MARK: assistant_text

    func testDecodeAssistantText() {
        let text = json([
            "event": "assistant_text",
            "text": "The answer is 42.",
            "final": true,
            "turn_id": "11",
        ])
        guard case .assistantText(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .assistantText")
        }
        XCTAssertEqual(f.text, "The answer is 42.")
        XCTAssertTrue(f.isFinal)
        XCTAssertEqual(f.turnID, "11")
    }

    // MARK: turn_completed

    func testDecodeTurnCompleted() {
        let text = json(["event": "turn_completed", "turn_id": "6"])
        guard case .turnCompleted(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .turnCompleted")
        }
        XCTAssertEqual(f.turnID, "6")
    }

    // MARK: turn_end

    func testDecodeTurnEndWithTurnID() {
        let text = json(["event": "turn_end", "turn_id": "8"])
        guard case .turnEnd(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .turnEnd")
        }
        XCTAssertEqual(f.turnID, "8")
    }

    func testDecodeTurnEndWithoutTurnID() {
        let text = json(["event": "turn_end"])
        guard case .turnEnd(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .turnEnd")
        }
        XCTAssertNil(f.turnID)
    }

    // MARK: voice_turn_skipped

    func testDecodeVoiceTurnSkipped() {
        let text = json([
            "event": "voice_turn_skipped",
            "reason": "audio_too_short",
            "turn_id": "1",
        ])
        guard case .voiceTurnSkipped(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .voiceTurnSkipped")
        }
        XCTAssertEqual(f.reason, "audio_too_short")
        XCTAssertEqual(f.turnID, "1")
    }

    // MARK: pong

    func testDecodePong() {
        let text = json(["event": "pong"])
        guard case .pong = InboundFrame.decode(from: text) else {
            return XCTFail("expected .pong")
        }
    }

    // MARK: error

    func testDecodeError() {
        let text = json([
            "event": "error",
            "error": ["code": "AUTH_FAILED", "message": "Authentication required", "status": 401],
        ])
        guard case .error(let f) = InboundFrame.decode(from: text) else {
            return XCTFail("expected .error")
        }
        XCTAssertEqual(f.error.code, "AUTH_FAILED")
        XCTAssertEqual(f.error.status, 401)
    }

    // MARK: unknown frames do not crash

    func testUnknownEventDoesNotCrash() {
        let text = json(["event": "brand_new_event_from_future", "some_field": "value"])
        if case .unknown(let raw) = InboundFrame.decode(from: text) {
            XCTAssertFalse(raw.isEmpty)
        }
        // Either .unknown or another case is acceptable; the important thing is no crash.
    }

    func testMalformedJSONReturnsUnknown() {
        let text = "not json at all {"
        guard case .unknown = InboundFrame.decode(from: text) else {
            return XCTFail("expected .unknown for malformed JSON")
        }
    }
}

// MARK: - VoiceSocket state-machine tests (fake-socket, no networking)

@MainActor
final class VoiceSocketStateMachineTests: XCTestCase {

    private func makeSocket() -> VoiceSocket {
        VoiceSocket(urlSession: .shared)   // urlSession is not used in these tests
    }

    // Helper: JSON string for a frame dict
    private func json(_ pairs: [String: Any]) -> String {
        let data = try! JSONSerialization.data(withJSONObject: pairs)
        return String(data: data, encoding: .utf8)!
    }

    // MARK: - Option A: normal flow

    func testNormalAudioChunkDelivered() {
        let socket = makeSocket()
        var delivered: (AudioChunkFrame, Data)?
        socket.onAudioChunk = { prelude, data in delivered = (prelude, data) }

        // Simulate turn_started so activeTurnID is set
        socket.processInboundText(json(["event": "turn_started", "turn_id": "1"]))
        XCTAssertEqual(socket.activeTurnID, "1")

        // Prelude arrives
        socket.processInboundText(json([
            "event": "audio_chunk", "turn_id": "1", "seq": 0, "format": "aac_adts", "bytes": 4,
        ]))
        XCTAssertNotNil(socket.pendingAudioChunk)

        // Binary arrives
        let payload = Data([0xAA, 0xBB, 0xCC, 0xDD])
        socket.processInboundBinary(payload)

        XCTAssertNotNil(delivered)
        XCTAssertEqual(delivered?.0.turnID, "1")
        XCTAssertEqual(delivered?.1, payload)
        XCTAssertNil(socket.pendingAudioChunk, "slot cleared after delivery")
    }

    // MARK: - Option A: binary without prelude is dropped

    func testBinaryWithoutPreludeIsDropped() {
        let socket = makeSocket()
        var delivered = false
        socket.onAudioChunk = { _, _ in delivered = true }

        socket.processInboundText(json(["event": "turn_started", "turn_id": "1"]))
        // No audio_chunk prelude — send binary directly
        socket.processInboundBinary(Data([0x01, 0x02]))

        XCTAssertFalse(delivered, "binary without prelude must be dropped")
    }

    // MARK: - Option A: stale prelude after cancel is dropped

    func testStaleAudioChunkAfterCancelIsDropped() async throws {
        let socket = makeSocket()
        var delivered = false
        socket.onAudioChunk = { _, _ in delivered = true }

        // Start turn
        socket.processInboundText(json(["event": "turn_started", "turn_id": "5"]))

        // Client cancels — clears activeTurnID
        try await socket.sendCancelTurn(turnID: "5")
        XCTAssertNil(socket.activeTurnID)

        // Server hasn't noticed yet; sends stale audio_chunk prelude for the old turn
        socket.processInboundText(json([
            "event": "audio_chunk", "turn_id": "5", "seq": 0, "format": "aac_adts", "bytes": 4,
        ]))

        // Followed by the binary
        socket.processInboundBinary(Data([0xDE, 0xAD, 0xBE, 0xEF]))

        XCTAssertFalse(delivered, "stale audio chunk after cancel must not be delivered")
    }

    // MARK: - Option A: next valid turn plays normally after cancel

    func testNextTurnPlaysAfterCancel() async throws {
        let socket = makeSocket()
        var deliveredTurnIDs: [String] = []
        socket.onAudioChunk = { prelude, _ in deliveredTurnIDs.append(prelude.turnID) }

        // Turn 1 starts then is cancelled
        socket.processInboundText(json(["event": "turn_started", "turn_id": "1"]))
        try await socket.sendCancelTurn(turnID: "1")

        // Stale chunk for turn 1 arrives and is dropped
        socket.processInboundText(json([
            "event": "audio_chunk", "turn_id": "1", "seq": 0, "format": "aac_adts", "bytes": 4,
        ]))
        socket.processInboundBinary(Data([0x00]))

        // New turn 2 starts and completes normally
        socket.processInboundText(json(["event": "turn_started", "turn_id": "2"]))
        socket.processInboundText(json([
            "event": "audio_chunk", "turn_id": "2", "seq": 0, "format": "aac_adts", "bytes": 4,
        ]))
        socket.processInboundBinary(Data([0xFF]))

        XCTAssertEqual(deliveredTurnIDs, ["2"], "only turn 2 chunk should be delivered")
    }

    // MARK: - Unknown frames do not crash or corrupt state

    func testUnknownFrameDoesNotCrashOrCorruptState() {
        let socket = makeSocket()
        socket.processInboundText(json(["event": "turn_started", "turn_id": "3"]))
        XCTAssertEqual(socket.activeTurnID, "3")

        // Unknown frame in the middle of a turn
        socket.processInboundText(json(["event": "some_future_event", "data": "extra"]))

        // Turn ID must still be intact
        XCTAssertEqual(socket.activeTurnID, "3")
    }

    // MARK: - active_state rendering

    func testActiveStateCallbackFired() {
        let socket = makeSocket()
        var receivedStates: [ActiveState] = []
        socket.onActiveState = { receivedStates.append($0.state) }

        socket.processInboundText(json(["event": "active_state", "state": "thinking", "turn_id": "1"]))
        socket.processInboundText(json(["event": "active_state", "state": "speaking", "turn_id": "1"]))
        socket.processInboundText(json(["event": "active_state", "state": "idle"]))

        XCTAssertEqual(receivedStates, [.thinking, .speaking, .idle])
    }

    // MARK: - turn_end clears activeTurnID

    func testTurnEndClearsActiveTurnID() {
        let socket = makeSocket()
        socket.processInboundText(json(["event": "turn_started", "turn_id": "9"]))
        XCTAssertEqual(socket.activeTurnID, "9")

        socket.processInboundText(json(["event": "turn_end", "turn_id": "9"]))
        XCTAssertNil(socket.activeTurnID)
    }

    // MARK: - session_started sets connection state and negotiated format

    func testSessionStartedSetsState() {
        let socket = makeSocket()
        socket.processInboundText(json([
            "event": "session_started",
            "conversation_id": "c42",
            "downlink_format": "wav_pcm16",
            "downlink_sample_rate": 16000,
            "downlink_channels": 1,
        ]))
        XCTAssertEqual(socket.connectionState, .connected)
        XCTAssertEqual(socket.conversationID, "c42")
        XCTAssertEqual(socket.negotiatedFormat, .wavPCM16)
        XCTAssertEqual(socket.negotiatedSampleRate, 16000)
    }
}
