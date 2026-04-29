from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def _fake_tts(text: str) -> bytes:
    return b"audio:" + text.encode()


async def _fake_hermes(text: str, cid: str, **kwargs):
    yield "a response"


def _make_callbacks():
    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []

    async def send_json(data: dict) -> None:
        sent_json.append(data)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    return sent_json, sent_bytes, send_json, send_bytes


async def test_short_audio_skips_stt_and_returns_idle():
    from app.services.pipeline import run_voice_turn

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()
    transcribe = AsyncMock(return_value="should not be called")

    with patch("app.services.pipeline.transcribe", transcribe):
        await run_voice_turn(
            audio_bytes=b"\x00" * 5,
            audio_format="wav",
            conversation_id="cid-short",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    transcribe.assert_not_called()
    assert sent_bytes == []
    assert {"event": "voice_turn_skipped", "reason": "audio_too_short"} in sent_json
    assert {"event": "active_state", "state": "idle"} in sent_json


async def test_normal_audio_still_reaches_stt():
    from app.services.pipeline import run_voice_turn

    sent_json, sent_bytes, send_json, send_bytes = _make_callbacks()
    transcribe = AsyncMock(return_value="hello")

    with (
        patch("app.services.pipeline.transcribe", transcribe),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-normal",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    transcribe.assert_awaited_once()
    assert sent_bytes
