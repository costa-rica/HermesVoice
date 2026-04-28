from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import httpx
from loguru import logger

from ..config import settings

ACCEPTED_ORIGINS = {
    "https://hermes-voice.dashanddata.com",
    "http://localhost:5173",
    "http://localhost:8700",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8700",
}

SPEAKABLE_EVENT = "response.output_text.delta"


async def stream_hermes_text(
    text: str,
    conversation_id: str,
) -> AsyncIterator[str]:
    """Stream speakable text deltas from Hermes, yielding one delta string at a time.

    Raises asyncio.CancelledError if the task is cancelled.
    Raises RuntimeError on Hermes connectivity or timeout errors.
    """
    url = settings.HERMES_BASE_URL.rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {settings.HERMES_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": settings.HERMES_MODEL,
        "input": text,
        "conversation": conversation_id,
        "stream": True,
    }

    inter_token_timeout = settings.HERMES_INTER_TOKEN_TIMEOUT
    request_timeout = settings.HERMES_REQUEST_TIMEOUT

    async with httpx.AsyncClient(timeout=httpx.Timeout(request_timeout)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"Hermes returned HTTP {resp.status_code}: {body.decode()[:200]}"
                )

            event_name: str | None = None
            last_event_time = time.monotonic()

            async for line in resp.aiter_lines():
                # Inter-token idle timeout check
                now = time.monotonic()
                if now - last_event_time > inter_token_timeout:
                    raise RuntimeError(
                        f"Hermes inter-token timeout ({inter_token_timeout}s) exceeded"
                    )
                last_event_time = now

                if not line:
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    etype = (
                        parsed.get("type")
                        if isinstance(parsed, dict)
                        else None
                    ) or event_name or ""

                    if etype == SPEAKABLE_EVENT:
                        delta = parsed.get("delta") if isinstance(parsed, dict) else None
                        if delta:
                            logger.debug(f"Hermes delta: {delta[:60]!r}")
                            yield delta
