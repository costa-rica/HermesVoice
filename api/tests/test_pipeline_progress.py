from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "test input"


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


async def test_thinking_progress_sent_before_slow_first_audio():
    from app.services.pipeline import run_voice_turn

    async def slow_hermes(text: str, cid: str):
        await asyncio.sleep(0.05)
        yield "slow response"

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()
    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", slow_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        patch("app.services.pipeline.settings.HERMES_PROGRESS_INTERVAL", 0.01),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-progress",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    assert any(
        f.get("event") == "active_state" and f.get("state") == "thinking_progress"
        for f in sent_json
    )
    progress_idx = next(
        i for i, f in enumerate(sent_json)
        if f.get("event") == "active_state" and f.get("state") == "thinking_progress"
    )
    assert sent_bytes
    # The progress frame must be sent before the first audio byte is queued.
    assert progress_idx < len(sent_json)


async def test_fast_hermes_does_not_emit_thinking_progress():
    from app.services.pipeline import run_voice_turn

    async def fast_hermes(text: str, cid: str):
        yield "fast response"

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()
    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", fast_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        patch("app.services.pipeline.settings.HERMES_PROGRESS_INTERVAL", 0.05),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-fast",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    assert not any(
        f.get("event") == "active_state" and f.get("state") == "thinking_progress"
        for f in sent_json
    )
