from __future__ import annotations

import asyncio
import math
import struct
import subprocess
import tempfile
import time
import wave
from collections.abc import AsyncIterator, Callable, Coroutine
from functools import lru_cache
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
_MOCK_TRANSCRIPT = "mock transcript for local mobile development"
_MOCK_ASSISTANT_TEXT = "Mock HermesVoice response for local mobile development."


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


def _mock_pcm16_audio(sample_rate: int = 16000, duration_seconds: float = 0.25) -> bytes:
    frame_count = int(sample_rate * duration_seconds)
    amplitude = 2000
    frequency = 440.0
    return b"".join(
        struct.pack(
            "<h",
            int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate))),
        )
        for i in range(frame_count)
    )


def _mock_audio_for_downlink(downlink_format: str) -> bytes:
    if downlink_format == "wav_pcm16":
        return _mock_pcm16_audio()
    if downlink_format == "aac_adts":
        return _mock_aac_adts_audio()
    return b"OggS mock-opus-ogg-local-dev-audio"


@lru_cache(maxsize=1)
def _mock_aac_adts_audio() -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = f"{tmpdir}/mock.wav"
        aac_path = f"{tmpdir}/mock.aac"
        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(_mock_pcm16_audio(sample_rate=24000))
        try:
            subprocess.run(
                ["afconvert", "-f", "adts", "-d", "aac", wav_path, aac_path],
                check=True,
                capture_output=True,
            )
            with open(aac_path, "rb") as audio_file:
                return audio_file.read()
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
            logger.warning(f"Unable to generate mock AAC ADTS audio: {exc!r}")
            return b"mock-aac-adts-local-dev-audio"


def _resample_pcm16_24k_to_16k(audio: bytes) -> bytes:
    if not audio or len(audio) % 2 != 0:
        return audio
    samples = struct.unpack(f"<{len(audio) // 2}h", audio)
    if len(samples) < 3:
        return audio
    downsampled: list[int] = []
    # Convert 24 kHz to 16 kHz by linearly interpolating every 1.5 input frames.
    output_count = int(len(samples) * 2 / 3)
    for i in range(output_count):
        src_pos = i * 1.5
        left = int(src_pos)
        right = min(left + 1, len(samples) - 1)
        frac = src_pos - left
        value = int(samples[left] * (1.0 - frac) + samples[right] * frac)
        downsampled.append(value)
    return struct.pack(f"<{len(downsampled)}h", *downsampled)


async def _run_mock_voice_turn(
    audio_bytes: bytes,
    audio_format: str,
    conversation_id: str,
    send_json: Callable[[dict], Coroutine[Any, Any, None]],
    send_bytes: Callable[[bytes], Coroutine[Any, Any, None]],
    turn_id: int,
    get_active_turn_id: Callable[[], int],
    downlink_format: str,
    sample_rate: int | None,
    utterance_buffer_ms: float | None,
) -> None:
    timer = TurnTimer(
        conversation_id=conversation_id,
        turn_id=turn_id,
        audio_bytes=len(audio_bytes),
        audio_format=audio_format,
        sample_rate=sample_rate,
        utterance_buffer_ms=utterance_buffer_ms,
    )
    timer.log("latency.mock_turn_started")
    wire_turn_id = str(turn_id)

    if len(audio_bytes) < settings.MIN_UTTERANCE_BYTES:
        await _skip_too_short_audio(timer, send_json, turn_id)
        return

    if get_active_turn_id() != turn_id:
        return

    await send_json({"event": "transcript", "text": _MOCK_TRANSCRIPT, "turn_id": wire_turn_id})
    await send_json({"event": "active_state", "state": "thinking", "turn_id": wire_turn_id})
    await send_json({"event": "turn_started", "turn_id": wire_turn_id})
    await asyncio.sleep(0)

    if get_active_turn_id() != turn_id:
        return

    await send_json({
        "event": "assistant_text",
        "text": _MOCK_ASSISTANT_TEXT,
        "final": True,
        "turn_id": wire_turn_id,
    })
    audio = _mock_audio_for_downlink(downlink_format)
    await send_json({
        "event": "audio_chunk",
        "turn_id": wire_turn_id,
        "seq": 0,
        "format": downlink_format,
        "bytes": len(audio),
    })
    await send_bytes(audio)
    await send_json({"event": "turn_completed", "turn_id": wire_turn_id})
    await send_json({"event": "active_state", "state": "idle"})
    await send_json({"event": "turn_end", "turn_id": wire_turn_id})

    timer.log(
        "latency.mock_turn_completed",
        total_ms=timer.elapsed_ms(),
        assistant_text_len=len(_MOCK_ASSISTANT_TEXT),
        tts_audio_bytes=len(audio),
    )


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
    if settings.HERMES_VOICE_MOCK_PIPELINE:
        logger.info("HERMES_VOICE_MOCK_PIPELINE enabled; using local mock voice turn")
        await _run_mock_voice_turn(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            conversation_id=conversation_id,
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=turn_id,
            get_active_turn_id=get_active_turn_id,
            downlink_format=downlink_format,
            sample_rate=sample_rate,
            utterance_buffer_ms=utterance_buffer_ms,
        )
        return

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
            # OpenAI TTS PCM is 24 kHz; the mobile fallback contract is 16 kHz.
            if downlink_format == "wav_pcm16":
                audio = _resample_pcm16_24k_to_16k(await synthesize(chunk, format="pcm"))
            else:
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
