from __future__ import annotations

import io
import time
from pathlib import Path

from loguru import logger
from openai import AsyncOpenAI

from ..config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


_FORMAT_MIME: dict[str, str] = {
    "wav": "audio/wav",
    "webm/opus": "audio/webm",
    "ogg/opus": "audio/ogg",
}

_FORMAT_EXTENSION: dict[str, str] = {
    "wav": "wav",
    "webm/opus": "webm",
    "ogg/opus": "ogg",
}

ACCEPTED_FORMATS = set(_FORMAT_MIME.keys())


async def transcribe(audio_bytes: bytes, audio_format: str) -> str:
    """Transcribe buffered audio bytes using Whisper. Returns transcript string."""
    if audio_format not in ACCEPTED_FORMATS:
        raise ValueError(f"Unsupported audio format: {audio_format!r}")

    ext = _FORMAT_EXTENSION[audio_format]
    filename = f"utterance.{ext}"

    logger.info(f"STT: {len(audio_bytes):,} bytes, format={audio_format!r}")

    client = _get_client()
    audio_file = (filename, io.BytesIO(audio_bytes), _FORMAT_MIME[audio_format])

    t0 = time.monotonic()
    result = await client.audio.transcriptions.create(
        model=settings.STT_MODEL,
        file=audio_file,
        response_format="text",
    )
    stt_ms = (time.monotonic() - t0) * 1000.0

    text = result if isinstance(result, str) else getattr(result, "text", str(result))
    transcript = text.strip()
    logger.info(f"STT: completed in {stt_ms:.0f}ms, {len(transcript)} chars")
    return transcript
