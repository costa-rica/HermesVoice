from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Hermes service tests
# ---------------------------------------------------------------------------


async def _fake_hermes_lines(lines: list[str]):
    for line in lines:
        yield line


def _make_hermes_response(events: list[tuple[str, str]]) -> list[str]:
    """Build SSE lines list from (event_type, delta) pairs."""
    result = []
    for etype, delta in events:
        result.append(f'data: {{"type":"{etype}","delta":"{delta}"}}')
        result.append("")
    result.append("data: [DONE]")
    return result


async def test_hermes_filters_speakable_events():
    """Only response.output_text.delta events produce text."""
    from app.services.hermes import stream_hermes_text

    sse_lines = [
        'data: {"type":"response.created","sequence_number":0}',
        "",
        'data: {"type":"response.output_text.delta","delta":"Hello "}',
        "",
        'data: {"type":"response.output_item.added","sequence_number":1}',
        "",
        'data: {"type":"response.output_text.delta","delta":"world"}',
        "",
        "data: [DONE]",
    ]

    async def fake_aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = fake_aiter_lines

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_stream = MagicMock()
    mock_stream.return_value = mock_ctx

    mock_client = MagicMock()
    mock_client.stream = mock_stream
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.hermes.httpx.AsyncClient", return_value=mock_client):
        result = []
        async for delta in stream_hermes_text("ping", "conv-1"):
            result.append(delta)

    assert result == ["Hello ", "world"]


async def test_hermes_ignores_non_speakable_events():
    """Tool-progress and other non-speakable events are silently dropped."""
    from app.services.hermes import stream_hermes_text

    sse_lines = [
        'data: {"type":"response.tool_call.started","name":"terminal"}',
        "",
        'data: {"type":"response.tool_call.done","name":"terminal"}',
        "",
        'data: {"type":"response.output_text.delta","delta":"done"}',
        "",
        "data: [DONE]",
    ]

    async def fake_aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = fake_aiter_lines

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.hermes.httpx.AsyncClient", return_value=mock_client):
        result = []
        async for delta in stream_hermes_text("ping", "conv-2"):
            result.append(delta)

    assert result == ["done"]


# ---------------------------------------------------------------------------
# STT service tests
# ---------------------------------------------------------------------------


async def test_stt_rejects_unknown_format():
    from app.services.stt import transcribe

    with pytest.raises(ValueError, match="Unsupported audio format"):
        await transcribe(b"\x00", "mp3")


async def test_stt_accepts_valid_formats():
    """Accepted format strings don't raise ValueError before hitting OpenAI."""
    from app.services.stt import ACCEPTED_FORMATS

    assert "wav" in ACCEPTED_FORMATS
    assert "webm/opus" in ACCEPTED_FORMATS
    assert "ogg/opus" in ACCEPTED_FORMATS


# ---------------------------------------------------------------------------
# Pipeline chunking tests
# ---------------------------------------------------------------------------


async def test_pipeline_chunks_by_sentence():
    """Sentence-ending punctuation triggers a flush when buffer >= min chars."""
    from app.services.pipeline import _chunk_hermes_text

    async def fake_stream(text, cid, **kwargs):
        words = "This is a longer sentence that ends with a period and has enough chars."
        for ch in words:
            yield ch

    with patch("app.services.pipeline.stream_hermes_text", fake_stream):
        chunks = []
        async for chunk, _full in _chunk_hermes_text("x", "cid"):
            chunks.append(chunk)

    assert len(chunks) >= 1
    full = "".join(chunks)
    assert "sentence" in full


async def test_pipeline_flushes_remaining_buffer():
    """After Hermes done, remaining text is flushed even without punctuation."""
    from app.services.pipeline import _chunk_hermes_text

    short_text = "short text"

    async def fake_stream(text, cid, **kwargs):
        for ch in short_text:
            yield ch

    with patch("app.services.pipeline.stream_hermes_text", fake_stream):
        chunks = []
        async for chunk, _full in _chunk_hermes_text("x", "cid"):
            chunks.append(chunk)

    assert "".join(chunks) == short_text


async def test_pipeline_cancellation_stops_audio():
    """Cancelling the turn task prevents further audio writes."""
    from app.services.pipeline import run_voice_turn

    sent_audio: list[bytes] = []
    sent_json: list[dict] = []
    turn_id_container = [1]

    async def send_json(data):
        sent_json.append(data)

    async def send_bytes(data):
        sent_audio.append(data)

    async def slow_stt(audio_bytes, audio_format):
        await asyncio.sleep(0.05)
        return "hello"

    async def slow_hermes(text, cid, **kwargs):
        for ch in "hello world":
            await asyncio.sleep(0.01)
            yield ch

    async def slow_tts(text):
        await asyncio.sleep(0.05)
        return b"audio:" + text.encode()

    with (
        patch("app.services.pipeline.transcribe", slow_stt),
        patch("app.services.pipeline.stream_hermes_text", slow_hermes),
        patch("app.services.pipeline.synthesize", slow_tts),
    ):
        task = asyncio.create_task(
            run_voice_turn(
                audio_bytes=b"\x00" * 100,
                audio_format="wav",
                conversation_id="cid",
                send_json=send_json,
                send_bytes=send_bytes,
                turn_id=1,
                get_active_turn_id=lambda: turn_id_container[0],
            )
        )
        await asyncio.sleep(0.03)
        turn_id_container[0] = 2  # Simulate cancellation via turn_id change
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(sent_audio) == 0, "No audio should be written after cancellation"
