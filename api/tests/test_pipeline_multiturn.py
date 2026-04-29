"""Phase 0 baseline tests for multi-turn pipeline behavior.

These tests drive run_voice_turn in isolation (mocked STT, Hermes, TTS) to
establish a reproducible signal for the frame sequence produced by one turn
and by two consecutive turns.  The tests live in api/tests/ per the project
convention and are referenced by
docs/requirements/20260428_TODO_HERMES_VOICE_CONVERSATION_FLOW.md Phase 0.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "hello world"


async def _fake_hermes(text: str, cid: str, **kwargs):
    yield "short reply"


async def _fake_tts(text: str) -> bytes:
    return b"audio:" + text.encode()


def _make_callbacks():
    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []

    async def send_json(data: dict) -> None:
        sent_json.append(data)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    return sent_json, sent_bytes, send_json, send_bytes


# ---------------------------------------------------------------------------
# Phase 0, test 1: single-turn frame sequence
# ---------------------------------------------------------------------------


async def test_single_turn_frame_sequence():
    """A complete turn emits transcript, turn_started, audio, turn_completed, turn_end."""
    from app.services.pipeline import run_voice_turn

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-1",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    assert events == [
        "transcript", "active_state", "turn_started",
        "active_state", "assistant_text", "turn_completed", "active_state", "turn_end",
    ], f"Unexpected frame sequence: {events}"
    assert sent_json[0]["text"] == "hello world"
    assert len(sent_bytes) >= 1, "Expected at least one audio chunk"


# ---------------------------------------------------------------------------
# Phase 0, test 2: two consecutive turns
# ---------------------------------------------------------------------------


async def test_two_consecutive_turns_both_complete():
    """Two sequential turns each produce the same complete frame sequence.

    This is the key multi-turn baseline.  If the second turn is broken in a
    future integration context, the analogous WebSocket-level test will catch
    it; this test proves the pipeline function itself is stateless between
    invocations.
    """
    from app.services.pipeline import run_voice_turn

    for turn_id in (1, 2):
        sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

        with (
            patch("app.services.pipeline.transcribe", _fake_stt),
            patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
            patch("app.services.pipeline.synthesize", _fake_tts),
        ):
            await run_voice_turn(
                audio_bytes=b"\x00" * 100,
                audio_format="wav",
                conversation_id="cid-multi",
                send_json=send_json,
                send_bytes=send_bytes,
                turn_id=turn_id,
                get_active_turn_id=lambda tid=turn_id: tid,
            )

        events = [f["event"] for f in sent_json]
        assert events == [
            "transcript", "active_state", "turn_started",
            "active_state", "assistant_text", "turn_completed", "active_state", "turn_end",
        ], f"Turn {turn_id} produced unexpected frame sequence: {events}"
        assert len(sent_bytes) >= 1, f"Turn {turn_id} produced no audio"


async def test_three_consecutive_turns_all_complete():
    """Three sequential turns each complete successfully — pipeline remains stateless."""
    from app.services.pipeline import run_voice_turn

    for turn_id in (1, 2, 3):
        sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

        with (
            patch("app.services.pipeline.transcribe", _fake_stt),
            patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
            patch("app.services.pipeline.synthesize", _fake_tts),
        ):
            await run_voice_turn(
                audio_bytes=b"\x00" * 100,
                audio_format="wav",
                conversation_id="cid-three",
                send_json=send_json,
                send_bytes=send_bytes,
                turn_id=turn_id,
                get_active_turn_id=lambda tid=turn_id: tid,
            )

        events = [f["event"] for f in sent_json]
        assert "turn_completed" in events, f"Turn {turn_id} did not complete"
        assert "assistant_text" in events, f"Turn {turn_id} missing assistant_text"
        assert len(sent_bytes) >= 1, f"Turn {turn_id} produced no audio"


# ---------------------------------------------------------------------------
# Phase 0, test 3: stale turn_id prevents audio write
# ---------------------------------------------------------------------------


async def test_stale_turn_id_suppresses_output():
    """If get_active_turn_id() returns a newer id after STT, no audio is sent.

    Guards the cancellation check in run_voice_turn: a new turn arriving while
    STT is in-flight must prevent the old turn from sending audio or
    turn_completed after the turn_id advances.

    The mock STT sets a flag then yields via asyncio.sleep(0) so the
    advance_turn() coroutine can run and update active_id before STT returns.
    """
    from app.services.pipeline import run_voice_turn

    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []
    stt_done = asyncio.Event()
    active_id = [1]

    async def slow_stt(audio_bytes, audio_format):
        stt_done.set()
        await asyncio.sleep(0)  # yield to let advance_turn() set active_id=2
        return "hello"

    async def fake_hermes(text, cid, **kwargs):
        yield "reply"

    async def fake_tts(text):
        return b"audio"

    async def send_json(data):
        sent_json.append(data)

    async def send_bytes(data):
        sent_bytes.append(data)

    async def advance_turn():
        await stt_done.wait()
        active_id[0] = 2  # now pipeline's next guard sees a different turn_id

    with (
        patch("app.services.pipeline.transcribe", slow_stt),
        patch("app.services.pipeline.stream_hermes_text", fake_hermes),
        patch("app.services.pipeline.synthesize", fake_tts),
    ):
        await asyncio.gather(
            run_voice_turn(
                audio_bytes=b"\x00" * 100,
                audio_format="wav",
                conversation_id="cid-stale",
                send_json=send_json,
                send_bytes=send_bytes,
                turn_id=1,
                get_active_turn_id=lambda: active_id[0],
            ),
            advance_turn(),
        )

    events = [f["event"] for f in sent_json]
    assert "turn_completed" not in events, (
        f"turn_completed must not be emitted for a superseded turn; got {events}"
    )
    assert len(sent_bytes) == 0, "No audio should be sent for a superseded turn"
