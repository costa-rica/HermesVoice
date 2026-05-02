from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..auth import AuthPrincipal, get_auth_principal, get_auth_principal_ws
from ..config import settings
from ..errors import error_response, ws_error_frame
from ..services.pipeline import run_voice_turn
from ..services.stt import ACCEPTED_FORMATS
from ..services import voice_store

router = APIRouter()

_PRODUCTION_ORIGINS = {"https://hermes-voice.dashanddata.com"}
# 50 ms was fine for local browser connections but too tight for mobile clients
# connecting over the internet (typical RTT 20-150 ms). 1 s gives plenty of
# headroom; web clients that don't send client_hello wait at most 1 s before
# session_started is emitted.
_CLIENT_HELLO_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class DownlinkChoice:
    format: str
    sample_rate: int
    channels: int


_SUPPORTED_DOWNLINKS: dict[str, DownlinkChoice] = {
    "aac_adts": DownlinkChoice("aac_adts", 24000, 1),
    "wav_pcm16": DownlinkChoice("wav_pcm16", 16000, 1),
    "opus_ogg": DownlinkChoice("opus_ogg", 24000, 1),
}
_WEB_DEFAULT_DOWNLINK = _SUPPORTED_DOWNLINKS["opus_ogg"]


class VoiceSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class VoiceSessionPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


def _auth_failed_response() -> JSONResponse:
    return error_response("AUTH_FAILED", "Authentication required", 401)


def _session_missing_response(session_id: str) -> JSONResponse:
    status = 403 if voice_store.session_exists(session_id) else 404
    if status == 403:
        return error_response(
            "VOICE_SESSION_FORBIDDEN",
            "Voice session is not available for this account",
            status,
        )
    return error_response("VOICE_SESSION_NOT_FOUND", "Voice session not found", status)


def _require_principal(request: Request) -> AuthPrincipal | JSONResponse:
    principal = get_auth_principal(request)
    if principal is None:
        return _auth_failed_response()
    return principal


def _session_payload(session: dict) -> dict:
    return {"session": session}


@router.get("/api/voice/sessions")
async def list_voice_sessions(request: Request) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    return JSONResponse({"sessions": voice_store.list_sessions(principal.owner_id)})


@router.post("/api/voice/sessions", status_code=201)
async def create_voice_session(
    body: VoiceSessionCreateRequest,
    request: Request,
) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    session = voice_store.create_session(principal.owner_id, title=body.title)
    return JSONResponse(_session_payload(session), status_code=201)


@router.get("/api/voice/sessions/{session_id}")
async def get_voice_session(session_id: str, request: Request) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    session = voice_store.get_session(principal.owner_id, session_id)
    if session is None:
        return _session_missing_response(session_id)
    return JSONResponse(_session_payload(session))


@router.patch("/api/voice/sessions/{session_id}")
async def patch_voice_session(
    session_id: str,
    body: VoiceSessionPatchRequest,
    request: Request,
) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    session = voice_store.patch_session(
        principal.owner_id,
        session_id,
        title=body.title if "title" in body.model_fields_set else ...,
        archived=body.archived,
    )
    if session is None:
        return _session_missing_response(session_id)
    return JSONResponse(_session_payload(session))


@router.delete("/api/voice/sessions/{session_id}")
async def delete_voice_session(session_id: str, request: Request) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    session = voice_store.archive_session(principal.owner_id, session_id)
    if session is None:
        return _session_missing_response(session_id)
    return JSONResponse({
        "ok": True,
        "session_id": session["id"],
        "archived_at": session["archived_at"],
    })


@router.get("/api/voice/sessions/{session_id}/messages")
async def list_voice_session_messages(session_id: str, request: Request) -> JSONResponse:
    principal = _require_principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    session = voice_store.get_session(principal.owner_id, session_id)
    if session is None:
        return _session_missing_response(session_id)
    return JSONResponse({"messages": voice_store.list_messages(principal.owner_id, session_id)})


def _check_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "")
    # Native mobile clients (iOS/Android) don't send Origin; browsers always do.
    # Allowing empty-origin requests preserves CSRF protection for browser clients.
    if not origin:
        return True
    if settings.RUN_ENVIRONMENT == "production":
        return origin in _PRODUCTION_ORIGINS
    return True


def _session_started_frame(
    conversation_id: str,
    downlink: DownlinkChoice,
    *,
    session_id: str | None = None,
    resumed: bool | None = None,
    created: bool | None = None,
) -> dict:
    frame = {
        "event": "session_started",
        "conversation_id": conversation_id,
        "downlink_format": downlink.format,
        "downlink_sample_rate": downlink.sample_rate,
        "downlink_channels": downlink.channels,
    }
    if session_id is not None:
        frame["session_id"] = session_id
    if resumed is not None:
        frame["resumed"] = resumed
    if created is not None:
        frame["created"] = created
    return frame


def _choose_downlink(frame: dict) -> DownlinkChoice | None:
    accepted = frame.get("accepted_downlink_formats")
    if not isinstance(accepted, list):
        return None
    for candidate in accepted:
        if isinstance(candidate, str) and candidate in _SUPPORTED_DOWNLINKS:
            return _SUPPORTED_DOWNLINKS[candidate]
    return None


async def _receive_client_hello(
    websocket: WebSocket,
) -> tuple[DownlinkChoice, dict | None, bool, dict | None]:
    """Return downlink, optional already-read non-hello message, supported flag, hello frame."""
    try:
        msg = await asyncio.wait_for(websocket.receive(), timeout=_CLIENT_HELLO_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return _WEB_DEFAULT_DOWNLINK, None, True, None

    if msg["type"] == "websocket.disconnect":
        return _WEB_DEFAULT_DOWNLINK, msg, True, None

    if msg["type"] != "websocket.receive" or "text" not in msg or msg["text"] is None:
        return _WEB_DEFAULT_DOWNLINK, msg, True, None

    try:
        frame = json.loads(msg["text"])
    except json.JSONDecodeError:
        return _WEB_DEFAULT_DOWNLINK, msg, True, None

    if frame.get("event") != "client_hello":
        return _WEB_DEFAULT_DOWNLINK, msg, True, None

    downlink = _choose_downlink(frame)
    if downlink is None:
        return _WEB_DEFAULT_DOWNLINK, None, False, frame
    return downlink, None, True, frame


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket) -> None:
    # Origin check
    if not _check_origin(websocket):
        await websocket.close(code=4003)
        return

    # Auth: session cookie or API key
    principal = get_auth_principal_ws(websocket)
    if principal is None:
        await websocket.accept()
        await websocket.send_json(ws_error_frame("AUTH_FAILED", "Authentication required", 401))
        await websocket.close(code=4001)
        return

    await websocket.accept()

    downlink, pending_msg, downlink_supported, hello_frame = await _receive_client_hello(websocket)
    if not downlink_supported:
        await websocket.send_json(
            ws_error_frame(
                "unsupported_downlink",
                "None of the requested downlink formats are supported",
                400,
            )
        )
        await websocket.close(code=4000)
        return

    requested_session_id = (
        hello_frame.get("session_id")
        if isinstance(hello_frame, dict) and isinstance(hello_frame.get("session_id"), str)
        else None
    )
    if requested_session_id:
        session = voice_store.get_session(
            principal.owner_id,
            requested_session_id,
            include_archived=False,
        )
        if session is None:
            exists = voice_store.session_exists(requested_session_id)
            if exists:
                await websocket.send_json(
                    ws_error_frame(
                        "VOICE_SESSION_FORBIDDEN",
                        "Voice session is not available for this account",
                        403,
                    )
                )
                await websocket.close(code=4003)
            else:
                await websocket.send_json(
                    ws_error_frame("VOICE_SESSION_NOT_FOUND", "Voice session not found", 404)
                )
                await websocket.close(code=4004)
            return
        resumed = True
        created = False
    else:
        session = voice_store.create_session(principal.owner_id)
        resumed = False
        created = True

    session_id = session["id"]
    conversation_id = session["conversation_id"]
    await websocket.send_json(
        _session_started_frame(
            conversation_id,
            downlink,
            session_id=session_id,
            resumed=resumed,
            created=created,
        )
    )

    audio_buffer: bytearray = bytearray()
    current_format: Optional[str] = None
    current_sample_rate: Optional[int] = None
    utterance_started: bool = False
    utterance_started_at: float | None = None

    active_task: Optional[asyncio.Task] = None
    turn_counter = 0
    active_wire_turn_id: str | None = None

    def get_active_turn_id() -> int:
        return turn_counter

    async def send_json(data: dict) -> None:
        try:
            await websocket.send_json(data)
        except Exception:
            return
        try:
            if data.get("event") == "transcript" and isinstance(data.get("text"), str):
                voice_store.add_message(
                    principal.owner_id,
                    session_id,
                    turn_id=str(data.get("turn_id")) if data.get("turn_id") is not None else None,
                    role="user",
                    text=data["text"],
                    final=True,
                    metadata={"source": "stt"},
                )
            elif (
                data.get("event") == "assistant_text"
                and data.get("final") is True
                and isinstance(data.get("text"), str)
            ):
                voice_store.add_message(
                    principal.owner_id,
                    session_id,
                    turn_id=str(data.get("turn_id")) if data.get("turn_id") is not None else None,
                    role="assistant",
                    text=data["text"],
                    final=True,
                    metadata={"source": "hermes"},
                )
        except Exception as exc:
            logger.warning(f"Unable to persist voice message: {exc!r}")

    async def send_bytes(data: bytes) -> None:
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass

    async def cancel_active_turn() -> str | None:
        nonlocal active_task, turn_counter, active_wire_turn_id
        canceled_turn_id = active_wire_turn_id
        if active_task and not active_task.done():
            turn_counter += 1
            active_task.cancel()
            try:
                await active_task
            except (asyncio.CancelledError, Exception):
                pass
        active_task = None
        active_wire_turn_id = None
        return canceled_turn_id

    try:
        idle_timeout = settings.IDLE_TIMEOUT

        while True:
            if pending_msg is not None:
                msg = pending_msg
                pending_msg = None
            else:
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
                        active_wire_turn_id = str(my_turn_id)

                        active_task = asyncio.create_task(
                            run_voice_turn(
                                audio_bytes=audio_data,
                                audio_format=audio_format,
                                conversation_id=conversation_id,
                                send_json=send_json,
                                send_bytes=send_bytes,
                                turn_id=my_turn_id,
                                get_active_turn_id=get_active_turn_id,
                                downlink_format=downlink.format,
                                sample_rate=current_sample_rate,
                                utterance_buffer_ms=utterance_buffer_ms,
                            )
                        )

                        def clear_completed_task(
                            task: asyncio.Task,
                            wire_turn_id: str = active_wire_turn_id,
                        ) -> None:
                            nonlocal active_task, active_wire_turn_id
                            if task is active_task and active_wire_turn_id == wire_turn_id:
                                active_task = None
                                active_wire_turn_id = None

                        active_task.add_done_callback(clear_completed_task)

                    elif event == "cancel_turn":
                        requested_turn_id = frame.get("turn_id")
                        canceled_turn_id = await cancel_active_turn()
                        if isinstance(requested_turn_id, str):
                            canceled_turn_id = requested_turn_id
                        audio_buffer.clear()
                        utterance_started = False
                        utterance_started_at = None
                        logger.info("cancel_turn received, active task cancelled")
                        await send_json({"event": "active_state", "state": "idle"})
                        turn_end = {"event": "turn_end"}
                        if canceled_turn_id is not None:
                            turn_end["turn_id"] = canceled_turn_id
                        await send_json(turn_end)

                    elif event == "ping":
                        pong: dict = {"event": "pong"}
                        if "id" in frame:
                            pong["id"] = frame["id"]
                        await send_json(pong)

                    elif event == "new_session":
                        await cancel_active_turn()
                        audio_buffer.clear()
                        utterance_started = False
                        utterance_started_at = None
                        session = voice_store.create_session(principal.owner_id)
                        session_id = session["id"]
                        conversation_id = session["conversation_id"]
                        await send_json(
                            _session_started_frame(
                                conversation_id,
                                downlink,
                                session_id=session_id,
                                resumed=False,
                                created=True,
                            )
                        )
                        logger.info(f"New session: {conversation_id}")

                    else:
                        logger.debug(f"Unknown WS event ignored: {event!r}")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception(f"WebSocket error: {exc}")
    finally:
        await cancel_active_turn()
