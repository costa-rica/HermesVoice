from __future__ import annotations

import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


def _test_client():
    from app.main import app
    from starlette.testclient import TestClient

    return TestClient(app)


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


async def test_client_hello_negotiation_aac_default(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "client": "ios",
                "client_version": "0.0.1",
                "accepted_downlink_formats": ["aac_adts", "mp3", "wav_pcm16", "opus_ogg"],
            }))

            msg = ws.receive_json()
            assert msg["event"] == "session_started"
            assert msg["downlink_format"] == "aac_adts"
            assert msg["downlink_sample_rate"] == 24000
            assert msg["downlink_channels"] == 1


async def test_client_hello_negotiation_pcm_fallback(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "client": "ios",
                "client_version": "0.0.1",
                "accepted_downlink_formats": ["wav_pcm16"],
            }))

            msg = ws.receive_json()
            assert msg["event"] == "session_started"
            assert msg["downlink_format"] == "wav_pcm16"
            assert msg["downlink_sample_rate"] == 16000
            assert msg["downlink_channels"] == 1


async def test_client_hello_unsupported_closes_with_typed_error(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "client": "ios",
                "client_version": "0.0.1",
                "accepted_downlink_formats": ["flac"],
            }))

            msg = ws.receive_json()
            assert msg["event"] == "error"
            assert msg["error"]["code"] == "unsupported_downlink"


async def test_web_path_without_client_hello_keeps_implicit_opus(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
            assert msg["downlink_format"] == "opus_ogg"
            assert msg["downlink_sample_rate"] == 24000
            assert msg["downlink_channels"] == 1


async def test_turn_id_present_on_all_turn_scoped_frames(client):
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
            conversation_id="cid-v06",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=7,
            get_active_turn_id=lambda: 7,
            downlink_format="aac_adts",
        )

    turn_scoped_events = {
        "turn_started",
        "transcript",
        "assistant_text",
        "audio_chunk",
        "turn_completed",
        "turn_end",
        "voice_turn_skipped",
    }
    for frame in sent_json:
        if frame.get("event") in turn_scoped_events:
            assert frame.get("turn_id") == "7", frame
        if frame.get("event") == "active_state" and frame.get("state") != "idle":
            assert frame.get("turn_id") == "7", frame

    assert sent_bytes


async def test_cancel_turn_echoes_turn_id(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"event": "cancel_turn", "turn_id": "turn-ios-1"}))

            frames = [ws.receive_json(), ws.receive_json()]
            turn_end = next(frame for frame in frames if frame.get("event") == "turn_end")
            assert turn_end["turn_id"] == "turn-ios-1"


async def test_audio_chunk_prelude_precedes_each_binary(client):
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
            conversation_id="cid-v06",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=3,
            get_active_turn_id=lambda: 3,
            downlink_format="aac_adts",
        )

    audio_chunks = [frame for frame in sent_json if frame.get("event") == "audio_chunk"]
    assert len(audio_chunks) == len(sent_bytes)
    assert [frame["seq"] for frame in audio_chunks] == list(range(len(sent_bytes)))


async def test_audio_chunk_bytes_match_binary_length(client):
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
            conversation_id="cid-v06",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=4,
            get_active_turn_id=lambda: 4,
            downlink_format="wav_pcm16",
        )

    audio_chunks = [frame for frame in sent_json if frame.get("event") == "audio_chunk"]
    assert [frame["bytes"] for frame in audio_chunks] == [len(data) for data in sent_bytes]
    assert all(frame["format"] == "wav_pcm16" for frame in audio_chunks)
