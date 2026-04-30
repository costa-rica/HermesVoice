from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from loguru import logger

from .hermes import VOICE_INSTRUCTIONS, stream_hermes_text
from .latency import TurnTimer
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
    on_first_delta: Callable[[], None] | None = None,
    *,
    source: str | None = None,
    instructions: str | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """Buffer Hermes text deltas and yield (tts_chunk, full_text_so_far) tuples.

    Yields one tuple per TTS-ready chunk.  The second element accumulates all
    deltas seen so far and is only complete on the final yield.  Callers that
    need the full transcript should use the last yielded second element.
    """
    buffer = ""
    full_text = ""
    first_buffered_at: float | None = None
    first_delta_fired = False

    async for delta in stream_hermes_text(text, conversation_id, source=source, instructions=instructions):
        if not first_delta_fired:
            first_delta_fired = True
            if on_first_delta is not None:
                on_first_delta()

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


async def _send_thinking_progress(
    send_json: Callable[[dict], Coroutine[Any, Any, None]],
    turn_id: int,
    get_active_turn_id: Callable[[], int],
    interval: float,
) -> None:
    """Emit periodic non-error progress frames while Hermes is still thinking."""
    try:
        while True:
            await asyncio.sleep(interval)
            if get_active_turn_id() != turn_id:
                return
            await send_json({
                "event": "active_state",
                "state": "thinking_progress",
                "turn_id": str(turn_id),
            })
    except asyncio.CancelledError:
        raise


async def _cancel_progress_task(task: asyncio.Task[None] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _skip_too_short_audio(
    timer: TurnTimer,
    send_json: Callable[[dict], Coroutine[Any, Any, None]],
    turn_id: int,
) -> None:
    timer.log(
        "latency.turn_skipped",
        reason="audio_too_short",
        min_utterance_bytes=settings.MIN_UTTERANCE_BYTES,
    )
    await send_json({
        "event": "voice_turn_skipped",
        "reason": "audio_too_short",
        "turn_id": str(turn_id),
    })
    await send_json({"event": "active_state", "state": "idle"})
    await send_json({"event": "turn_end", "turn_id": str(turn_id)})


async def run_voice_turn(
    audio_bytes: bytes,
    audio_format: str,
    conversation_id: str,
    send_json: Callable[[dict], Coroutine[Any, Any, None]],
    send_bytes: Callable[[bytes], Coroutine[Any, Any, None]],
    turn_id: int,
    get_active_turn_id: Callable[[], int],
    downlink_format: str = "opus_ogg",
    sample_rate: int | None = None,
    utterance_buffer_ms: float | None = None,
) -> None:
    """Full STT -> Hermes -> TTS pipeline for one utterance.

    send_json and send_bytes are callables to push frames to the WebSocket.
    turn_id / get_active_turn_id guard against cancelled turns writing stale audio.
    """
    timer = TurnTimer(
        conversation_id=conversation_id,
        turn_id=turn_id,
        audio_bytes=len(audio_bytes),
        audio_format=audio_format,
        sample_rate=sample_rate,
        utterance_buffer_ms=utterance_buffer_ms,
    )
    timer.log("latency.turn_started")
    progress_task: asyncio.Task[None] | None = None
    wire_turn_id = str(turn_id)

    try:
        if len(audio_bytes) < settings.MIN_UTTERANCE_BYTES:
            await _skip_too_short_audio(timer, send_json, turn_id)
            return

        # STT
        timer.mark("stt_start")
        transcript = await transcribe(audio_bytes, audio_format)
        timer.log(
            "latency.stt_completed",
            stt_ms=timer.delta_ms("stt_start"),
            transcript_len=len(transcript),
        )

        if get_active_turn_id() != turn_id:
            return

        await send_json({"event": "transcript", "text": transcript, "turn_id": wire_turn_id})
        await send_json({"event": "active_state", "state": "thinking", "turn_id": wire_turn_id})
        await send_json({"event": "turn_started", "turn_id": wire_turn_id})

        # Hermes -> TTS pipeline; accumulate full text for assistant_text frame
        full_assistant_text = ""
        first_chunk = True
        chunk_count = 0
        timer.mark("hermes_start")
        progress_task = asyncio.create_task(
            _send_thinking_progress(
                send_json,
                turn_id,
                get_active_turn_id,
                settings.HERMES_PROGRESS_INTERVAL,
            )
        )

        def _on_first_delta() -> None:
            timer.mark("hermes_first_delta")
            timer.log(
                "latency.hermes_first_delta",
                hermes_connect_ms=timer.delta_ms("hermes_start"),
            )
            if progress_task is not None:
                progress_task.cancel()

        async for chunk, full_text in _chunk_hermes_text(
            transcript, conversation_id, on_first_delta=_on_first_delta,
            source="voice", instructions=VOICE_INSTRUCTIONS,
        ):
            full_assistant_text = full_text
            if get_active_turn_id() != turn_id:
                logger.info(f"Turn {turn_id} cancelled mid-pipeline, dropping chunk")
                return

            timer.mark("tts_start")
            audio = await synthesize(chunk)
            timer.log(
                "latency.tts_completed",
                chunk_n=chunk_count,
                tts_ms=timer.delta_ms("tts_start"),
                chunk_chars=len(chunk),
                tts_audio_bytes=len(audio),
            )

            if get_active_turn_id() != turn_id:
                logger.info(f"Turn {turn_id} cancelled after TTS, not sending audio")
                return

            if first_chunk:
                first_chunk = False
                timer.log(
                    "latency.first_audio_sent",
                    first_audio_from_turn_start_ms=timer.elapsed_ms(),
                )
                await send_json({"event": "active_state", "state": "speaking", "turn_id": wire_turn_id})

            await send_json({
                "event": "audio_chunk",
                "turn_id": wire_turn_id,
                "seq": chunk_count,
                "format": downlink_format,
                "bytes": len(audio),
            })
            await send_bytes(audio)
            chunk_count += 1

        if get_active_turn_id() != turn_id:
            return

        timer.log(
            "latency.hermes_completed",
            hermes_total_ms=timer.delta_ms("hermes_start"),
            assistant_text_len=len(full_assistant_text),
            chunks=chunk_count,
        )

        if full_assistant_text:
            await send_json({
                "event": "assistant_text",
                "text": full_assistant_text,
                "final": True,
                "turn_id": wire_turn_id,
            })

        await send_json({"event": "turn_completed", "turn_id": wire_turn_id})
        await send_json({"event": "active_state", "state": "idle"})
        await send_json({"event": "turn_end", "turn_id": wire_turn_id})

        timer.log(
            "latency.turn_completed",
            total_ms=timer.elapsed_ms(),
            chunks=chunk_count,
            assistant_text_len=len(full_assistant_text),
        )

    except asyncio.CancelledError:
        logger.info(f"Turn {turn_id} cancelled")
        raise
    except Exception as exc:
        timer.log("latency.turn_failed", total_ms=timer.elapsed_ms(), error=repr(exc))
        logger.exception(f"Turn {turn_id} pipeline error: {exc}")
        if get_active_turn_id() == turn_id:
            await send_json({
                "event": "error",
                "error": {"code": "INTERNAL_ERROR", "message": "Voice turn failed", "status": 500},
            })
    finally:
        await _cancel_progress_task(progress_task)
