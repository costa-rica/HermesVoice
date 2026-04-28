from __future__ import annotations

import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response, WebSocket
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from loguru import logger

from .config import settings


_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="hermes-voice-session")

_SESSION_COOKIE = "hv_session"

_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_WINDOW = 60.0
_LOGIN_MAX_ATTEMPTS = 5


def _is_production() -> bool:
    return settings.RUN_ENVIRONMENT == "production"


def create_session_cookie(response: Response) -> None:
    token = _serializer.dumps("authenticated")
    cookie_kwargs: dict = {
        "key": _SESSION_COOKIE,
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "max_age": settings.SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }
    if _is_production():
        cookie_kwargs["secure"] = True
        cookie_kwargs["domain"] = ".hermes-voice.dashanddata.com"
    response.set_cookie(**cookie_kwargs)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(_SESSION_COOKIE, path="/")


def verify_session(request: Request) -> bool:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return True
    except SignatureExpired:
        logger.debug("Session cookie expired")
        return False
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        return False


def verify_session_ws(websocket: WebSocket) -> bool:
    token = websocket.cookies.get(_SESSION_COOKIE)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return True
    except (SignatureExpired, BadSignature):
        return False


def verify_api_key(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        return key == settings.HERMES_VOICE_API_KEY
    return False


def verify_api_key_ws(websocket: WebSocket) -> bool:
    auth_header = websocket.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        return key == settings.HERMES_VOICE_API_KEY
    return False


def check_rate_limit(ip: str) -> tuple[bool, Optional[float]]:
    now = time.monotonic()
    window_start = now - _LOGIN_RATE_WINDOW
    attempts = _login_attempts[ip]
    _login_attempts[ip] = [t for t in attempts if t > window_start]
    if len(_login_attempts[ip]) >= _LOGIN_MAX_ATTEMPTS:
        retry_after = _login_attempts[ip][0] + _LOGIN_RATE_WINDOW - now
        return False, max(retry_after, 0.0)
    _login_attempts[ip].append(now)
    return True, None
