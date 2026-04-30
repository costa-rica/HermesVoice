from __future__ import annotations

from loguru import logger
from openai import AsyncOpenAI

from ..config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.TTS_REQUEST_TIMEOUT,
        )
    return _client


async def synthesize(text: str, format: str | None = None) -> bytes:
    """Convert a text chunk to audio bytes via OpenAI TTS. Returns complete audio bytes."""
    fmt = format or settings.TTS_FORMAT
    logger.info(f"TTS: synthesizing {len(text)} chars (format={fmt!r}): {text[:60]!r}")
    client = _get_client()

    response = await client.audio.speech.create(
        model=settings.TTS_MODEL,
        voice=settings.TTS_VOICE,
        input=text,
        response_format=fmt,
    )

    audio_bytes = response.content
    logger.info(f"TTS: got {len(audio_bytes):,} bytes")
    return audio_bytes
