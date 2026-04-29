from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from loguru import logger

from .hermes import stream_hermes_text
from .stt import transcribe
from .tts import synthesize
from ..config import settings

_MIN_FLUSH_CHARS = 80
_MAX_FLUSH_CHARS = 280
_FORCE_FLUSH_SECONDS = 2.0
_SENTENCE_ENDINGS = frozenset(".?!\n")
_CLAUSE_ENDINGS = frozenset(",;:")


async def _chunk_hermes_text(
    text: str,
    conversation_id: str,
) -> AsyncIterator[tuple[str, str]]:
    """Buffer Hermes text deltas and yield (tts_chunk, full_text_so_far) tuples.

    Yields one tuple per TTS-ready chunk.  The second element accumulates all
    deltas seen so far and is only complete on the final yield.  Callers that
    need the full transcript should use the last yielded second element.
    """
    buffer = ""
    full_text = ""
    first_buffered_at: float | None = None

    async for delta in stream_hermes_text(text, conversation_id):
        full_text += delta
        buffer += delta
        if first_buffered_at is None and buffer.strip():
            first_buffered_at = time.monotonic()

        should_flush = False

        if len(buffer) >= _MAX_FLUSH_CHARS:
            should_flush = True
        elif buffer and buffer[-1] in _SENTENCE_ENDINGS and len(buffer) >= _MIN_FLUSH_CHARS:
            should_flush = True
        elif buffer and buffer[-1] in _CLAUSE_ENDINGS and len(buffer) >= _MIN_FLUSH_CHARS:
            should_flush = True
        elif (
            first_buffered_at is not None
            and time.monotonic() - first_buffered_at >= _FORCE_FLUSH_SECONDS
            and buffer.strip()
        ):
            should_flush = True

        if should_flush:
            chunk = buffer.strip()
            buffer = ""
            first_buffered_at = None
            if chunk:
                yield chunk, full_text

    if buffer.strip():
        yield buffer.strip(), full_text


async def run_voice_turn(
    audio_bytes: bytes,
    audio_format: str,
    conversation_id: str,
    send_json: Callable[[dict], Coroutine[Any, Any, None]],
    send_bytes: Callable[[bytes], Coroutine[Any, Any, None]],
    turn_id: int,
    get_active_turn_id: Callable[[], int],
) -> None:
    """Full STT -> Hermes -> TTS pipeline for one utterance.

    send_json and send_bytes are callables to push frames to the WebSocket.
    turn_id / get_active_turn_id guard against cancelled turns writing stale audio.
    """
    try:
        # STT
        transcript = await transcribe(audio_bytes, audio_format)
        if get_active_turn_id() != turn_id:
            return

        await send_json({"event": "transcript", "text": transcript})
        await send_json({"event": "turn_started"})

        # Hermes -> TTS pipeline; accumulate full text for assistant_text frame
        full_assistant_text = ""
        async for chunk, full_text in _chunk_hermes_text(transcript, conversation_id):
            full_assistant_text = full_text
            if get_active_turn_id() != turn_id:
                logger.info(f"Turn {turn_id} cancelled mid-pipeline, dropping chunk")
                return

            audio = await synthesize(chunk)

            if get_active_turn_id() != turn_id:
                logger.info(f"Turn {turn_id} cancelled after TTS, not sending audio")
                return

            await send_bytes(audio)

        if get_active_turn_id() != turn_id:
            return

        if full_assistant_text:
            await send_json({"event": "assistant_text", "text": full_assistant_text, "final": True})

        await send_json({"event": "turn_completed"})
        await send_json({"event": "turn_end"})

    except asyncio.CancelledError:
        logger.info(f"Turn {turn_id} cancelled")
        raise
    except Exception as exc:
        logger.exception(f"Turn {turn_id} pipeline error: {exc}")
        if get_active_turn_id() == turn_id:
            await send_json({
                "event": "error",
                "error": {"code": "INTERNAL_ERROR", "message": "Voice turn failed", "status": 500},
            })
