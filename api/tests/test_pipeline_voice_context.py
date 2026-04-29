"""Tests: pipeline passes voice context (source, instructions) to stream_hermes_text.

Referenced by:
  docs/requirements/20260429_TODO_HERMES_VOICE_CONVERSATIONAL_RESPONSES.md
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "hello"


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


async def test_run_voice_turn_passes_source_voice_to_hermes():
    """run_voice_turn passes source='voice' to stream_hermes_text."""
    from app.services.pipeline import run_voice_turn

    captured: list[dict] = []

    async def capturing_hermes(text, cid, *, source=None, instructions=None, **kwargs):
        captured.append({"source": source, "instructions": instructions})
        yield "reply"

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", capturing_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-vc",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    assert len(captured) == 1, "Expected exactly one Hermes call"
    assert captured[0]["source"] == "voice", f"Expected source='voice', got {captured[0]['source']!r}"


async def test_run_voice_turn_passes_voice_instructions_to_hermes():
    """run_voice_turn passes VOICE_INSTRUCTIONS constant to stream_hermes_text."""
    from app.services.pipeline import run_voice_turn
    from app.services.hermes import VOICE_INSTRUCTIONS

    captured: list[dict] = []

    async def capturing_hermes(text, cid, *, source=None, instructions=None, **kwargs):
        captured.append({"source": source, "instructions": instructions})
        yield "reply"

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", capturing_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-vc2",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    assert len(captured) == 1
    assert captured[0]["instructions"] == VOICE_INSTRUCTIONS, (
        f"Expected VOICE_INSTRUCTIONS, got {captured[0]['instructions']!r}"
    )
    assert VOICE_INSTRUCTIONS, "VOICE_INSTRUCTIONS must be a non-empty string"
