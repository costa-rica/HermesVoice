"""Phase 2 tests: pipeline emits assistant_text frame with concatenated Hermes text.

Referenced by:
  docs/requirements/20260428_TODO_HERMES_VOICE_CONVERSATION_FLOW.md Phase 2
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "tell me a story"


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


async def _multi_delta_hermes(text: str, cid: str, **kwargs):
    yield "Once upon "
    yield "a time "
    yield "in a land far away."


async def test_assistant_text_frame_emitted():
    """pipeline emits assistant_text with concatenated Hermes deltas before turn_completed."""
    from app.services.pipeline import run_voice_turn

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _multi_delta_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-p2",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    assert "assistant_text" in events, f"assistant_text missing from frames: {events}"

    idx = events.index("assistant_text")
    completed_idx = events.index("turn_completed")
    assert idx < completed_idx, "assistant_text must come before turn_completed"

    frame = sent_json[idx]
    assert frame.get("final") is True, "assistant_text frame must have final=true"
    assert frame["text"] == "Once upon a time in a land far away.", (
        f"Unexpected concatenated text: {frame['text']!r}"
    )


async def test_assistant_text_single_delta():
    """Works correctly when Hermes yields a single delta."""
    from app.services.pipeline import run_voice_turn

    async def single_delta(text: str, cid: str, **kwargs):
        yield "short reply"

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", single_delta),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-p2-single",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    events = [f["event"] for f in sent_json]
    assert "assistant_text" in events
    at_frame = next(f for f in sent_json if f["event"] == "assistant_text")
    assert at_frame["text"] == "short reply"
    assert at_frame["final"] is True
