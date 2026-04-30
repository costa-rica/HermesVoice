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

VOICE_INSTRUCTIONS = (
    "Respond conversationally and concisely. "
    "Avoid markdown, bullet points, numbered lists, and headers unless explicitly requested. "
    "Prefer short spoken answers. "
    "Do not read out URLs or code verbatim unless asked."
)


async def _next_line_with_timeout(
    iterator: AsyncIterator[str],
    timeout: float,
    timeout_message: str,
    timeout_event: str,
    *,
    conversation_id: str,
) -> str:
    try:
        return await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
    except StopAsyncIteration:
        raise
    except asyncio.TimeoutError as exc:
        logger.info(
            f"{timeout_event} | cid={conversation_id} timeout_s={timeout:.1f}"
        )
        raise RuntimeError(timeout_message) from exc


async def stream_hermes_text(
    text: str,
    conversation_id: str,
    *,
    source: str | None = None,
    instructions: str | None = None,
) -> AsyncIterator[str]:
    """Stream speakable text deltas from Hermes, yielding one delta string at a time.

    Raises asyncio.CancelledError if the task is cancelled.
    Raises RuntimeError on Hermes connectivity or categorized timeout errors.
    """
    url = settings.HERMES_BASE_URL.rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {settings.HERMES_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload: dict = {
        "model": settings.HERMES_MODEL,
        "input": text,
        "conversation": conversation_id,
        "stream": True,
    }
    if source is not None:
        payload["source"] = source
    if instructions is not None:
        payload["instructions"] = instructions

    first_event_timeout = settings.HERMES_FIRST_EVENT_TIMEOUT
    first_delta_timeout = settings.HERMES_FIRST_DELTA_TIMEOUT
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
            first_event_at: float | None = None
            first_delta_at: float | None = None
            last_delta_at: float | None = None
            max_inter_delta_gap_ms = 0.0
            line_iter = resp.aiter_lines().__aiter__()

            while True:
                if first_event_at is None:
                    timeout = first_event_timeout
                    timeout_message = (
                        f"Hermes first event timeout ({first_event_timeout:g}s) exceeded"
                    )
                    timeout_event = "latency.hermes_first_event_timeout"
                elif first_delta_at is None:
                    timeout = first_delta_timeout
                    timeout_message = (
                        f"Hermes first delta timeout ({first_delta_timeout:g}s) exceeded"
                    )
                    timeout_event = "latency.hermes_first_delta_timeout"
                else:
                    timeout = inter_token_timeout
                    timeout_message = (
                        f"Hermes inter-token timeout ({inter_token_timeout:g}s) exceeded"
                    )
                    timeout_event = "latency.hermes_inter_token_timeout"

                try:
                    line = await _next_line_with_timeout(
                        line_iter,
                        timeout,
                        timeout_message,
                        timeout_event,
                        conversation_id=conversation_id,
                    )
                except StopAsyncIteration:
                    if max_inter_delta_gap_ms:
                        logger.info(
                            "latency.hermes_stream_completed | "
                            f"cid={conversation_id} "
                            f"hermes_max_inter_delta_gap_ms={max_inter_delta_gap_ms:.1f}"
                        )
                    return

                now = time.monotonic()
                if first_event_at is None and line:
                    first_event_at = now
                    logger.info(
                        f"latency.hermes_first_event | cid={conversation_id} "
                        "hermes_first_event_ms=0.0"
                    )

                if not line:
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        if max_inter_delta_gap_ms:
                            logger.info(
                                "latency.hermes_stream_completed | "
                                f"cid={conversation_id} "
                                f"hermes_max_inter_delta_gap_ms={max_inter_delta_gap_ms:.1f}"
                            )
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
                            if first_delta_at is None:
                                first_delta_at = now
                                first_delta_ms = (
                                    (first_delta_at - first_event_at) * 1000.0
                                    if first_event_at is not None
                                    else 0.0
                                )
                                logger.info(
                                    "latency.hermes_first_speakable_delta | "
                                    f"cid={conversation_id} "
                                    f"hermes_first_speakable_delta_ms={first_delta_ms:.1f}"
                                )
                            if last_delta_at is not None:
                                max_inter_delta_gap_ms = max(
                                    max_inter_delta_gap_ms,
                                    (now - last_delta_at) * 1000.0,
                                )
                            last_delta_at = now
                            logger.debug(f"Hermes delta: {delta[:60]!r}")
                            yield delta
