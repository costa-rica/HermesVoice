"""Phase 3 tests: pipeline emits active_state frames at correct points in a turn.

Referenced by:
  docs/requirements/20260428_TODO_HERMES_VOICE_CONVERSATION_FLOW.md Phase 3

Expected active_state sequence for one turn (server-emitted):
  thinking  — after STT completes
  speaking  — on first audio chunk (before send_bytes)
  idle      — after turn_completed
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "test input"


async def _fake_tts(text: str) -> bytes:
    return b"audio:" + text.encode()


async def _fake_hermes(text: str, cid: str):
    yield "a response"


def _make_callbacks():
    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []

    async def send_json(data: dict) -> None:
        sent_json.append(data)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    return sent_json, sent_bytes, send_json, send_bytes


async def test_active_state_transition_order():
    """active_state frames emitted: thinking after STT, speaking before audio, idle at end."""
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
            conversation_id="cid-p3",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    active_states = [f["state"] for f in sent_json if f["event"] == "active_state"]

    assert "active_state" in events, f"No active_state frames found: {events}"
    assert "thinking" in active_states, f"thinking state missing: {active_states}"
    assert "speaking" in active_states, f"speaking state missing: {active_states}"
    assert "idle" in active_states, f"idle state missing: {active_states}"

    # thinking must come before speaking
    thinking_idx = next(i for i, f in enumerate(sent_json) if f.get("event") == "active_state" and f.get("state") == "thinking")
    speaking_idx = next(i for i, f in enumerate(sent_json) if f.get("event") == "active_state" and f.get("state") == "speaking")
    idle_idx = next(i for i, f in enumerate(sent_json) if f.get("event") == "active_state" and f.get("state") == "idle")

    assert thinking_idx < speaking_idx, "thinking must precede speaking"
    assert speaking_idx < idle_idx, "speaking must precede idle"


async def test_active_state_thinking_after_transcript():
    """thinking active_state comes after transcript frame."""
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
            conversation_id="cid-p3b",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    transcript_idx = events.index("transcript")
    thinking_idx = next(
        i for i, f in enumerate(sent_json)
        if f.get("event") == "active_state" and f.get("state") == "thinking"
    )
    assert thinking_idx > transcript_idx, "thinking must come after transcript"


async def test_active_state_idle_after_turn_completed():
    """idle active_state comes after turn_completed."""
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
            conversation_id="cid-p3c",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    completed_idx = events.index("turn_completed")
    idle_idx = next(
        i for i, e in enumerate(events)
        if e == "active_state" and sent_json[i].get("state") == "idle"
    )
    assert idle_idx > completed_idx, "idle must come after turn_completed"
