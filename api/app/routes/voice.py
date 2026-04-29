from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from ..auth import verify_api_key_ws, verify_session_ws
from ..config import settings
from ..errors import ws_error_frame
from ..services.pipeline import run_voice_turn
from ..services.stt import ACCEPTED_FORMATS

router = APIRouter()

_PRODUCTION_ORIGINS = {"https://hermes-voice.dashanddata.com"}


def _check_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "")
    if settings.RUN_ENVIRONMENT == "production":
        return origin in _PRODUCTION_ORIGINS
    return True


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket) -> None:
    # Origin check
    if not _check_origin(websocket):
        await websocket.close(code=4003)
        return

    # Auth: session cookie or API key
    if not verify_session_ws(websocket) and not verify_api_key_ws(websocket):
        await websocket.accept()
        await websocket.send_json(ws_error_frame("AUTH_FAILED", "Authentication required", 401))
        await websocket.close(code=4001)
        return

    await websocket.accept()

    conversation_id = str(uuid.uuid4())
    await websocket.send_json({"event": "session_started", "conversation_id": conversation_id})

    audio_buffer: bytearray = bytearray()
    current_format: Optional[str] = None
    current_sample_rate: Optional[int] = None
    utterance_started: bool = False
    utterance_started_at: float | None = None

    active_task: Optional[asyncio.Task] = None
    turn_counter = 0

    def get_active_turn_id() -> int:
        return turn_counter

    async def send_json(data: dict) -> None:
        try:
            await websocket.send_json(data)
        except Exception:
            pass

    async def send_bytes(data: bytes) -> None:
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass

    async def cancel_active_turn() -> None:
        nonlocal active_task, turn_counter
        if active_task and not active_task.done():
            turn_counter += 1
            active_task.cancel()
            try:
                await active_task
            except (asyncio.CancelledError, Exception):
                pass
        active_task = None

    try:
        idle_timeout = settings.IDLE_TIMEOUT

        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=idle_timeout)
            except asyncio.TimeoutError:
                logger.info("WebSocket idle timeout, closing")
                await websocket.send_json(
                    ws_error_frame("IDLE_TIMEOUT", "Connection idle timeout", 408)
                )
                break

            if msg["type"] == "websocket.disconnect":
                break

            if msg["type"] == "websocket.receive":
                if "bytes" in msg and msg["bytes"] is not None:
                    data: bytes = msg["bytes"]
                    if not utterance_started:
                        await send_json(
                            ws_error_frame(
                                "PROTOCOL_ERROR",
                                "Binary audio received before start_utterance",
                                400,
                            )
                        )
                        continue

                    if active_task and not active_task.done():
                        # V1 interrupt policy: ignore binary audio while turn is active
                        continue

                    if len(audio_buffer) + len(data) > settings.MAX_UTTERANCE_BYTES:
                        await send_json(
                            ws_error_frame(
                                "UTTERANCE_TOO_LARGE",
                                f"Utterance exceeds {settings.MAX_UTTERANCE_BYTES:,} bytes",
                                413,
                            )
                        )
                        audio_buffer.clear()
                        utterance_started = False
                        utterance_started_at = None
                        continue

                    audio_buffer.extend(data)

                elif "text" in msg and msg["text"] is not None:
                    try:
                        frame = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        await send_json(
                            ws_error_frame("PROTOCOL_ERROR", "Invalid JSON frame", 400)
                        )
                        continue

                    event = frame.get("event", "")

                    if event == "start_utterance":
                        fmt = frame.get("format")
                        if not fmt:
                            await send_json(
                                ws_error_frame("PROTOCOL_ERROR", "Missing format in start_utterance", 400)
                            )
                            continue
                        if fmt not in ACCEPTED_FORMATS:
                            await send_json(
                                ws_error_frame(
                                    "UNSUPPORTED_FORMAT",
                                    f"Unsupported audio format: {fmt!r}. "
                                    f"Accepted: {sorted(ACCEPTED_FORMATS)}",
                                    400,
                                )
                            )
                            continue
                        current_format = fmt
                        current_sample_rate = frame.get("sample_rate")
                        audio_buffer.clear()
                        utterance_started = True
                        utterance_started_at = time.monotonic()
                        logger.info(f"start_utterance: format={fmt!r} sample_rate={current_sample_rate}")

                    elif event == "end_of_utterance":
                        if not utterance_started or not audio_buffer:
                            await send_json(
                                ws_error_frame("PROTOCOL_ERROR", "No audio buffered for end_of_utterance", 400)
                            )
                            continue

                        audio_data = bytes(audio_buffer)
                        audio_format = current_format
                        utterance_buffer_ms = (
                            (time.monotonic() - utterance_started_at) * 1000.0
                            if utterance_started_at is not None
                            else None
                        )
                        audio_buffer.clear()
                        utterance_started = False
                        utterance_started_at = None

                        await cancel_active_turn()
                        turn_counter += 1
                        my_turn_id = turn_counter

                        active_task = asyncio.create_task(
                            run_voice_turn(
                                audio_bytes=audio_data,
                                audio_format=audio_format,
                                conversation_id=conversation_id,
                                send_json=send_json,
                                send_bytes=send_bytes,
                                turn_id=my_turn_id,
                                get_active_turn_id=get_active_turn_id,
                                sample_rate=current_sample_rate,
                                utterance_buffer_ms=utterance_buffer_ms,
                            )
                        )

                    elif event == "new_session":
                        await cancel_active_turn()
                        audio_buffer.clear()
                        utterance_started = False
                        utterance_started_at = None
                        conversation_id = str(uuid.uuid4())
                        await send_json({"event": "session_started", "conversation_id": conversation_id})
                        logger.info(f"New session: {conversation_id}")

                    else:
                        logger.debug(f"Unknown WS event ignored: {event!r}")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception(f"WebSocket error: {exc}")
    finally:
        await cancel_active_turn()
