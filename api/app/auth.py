from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import hmac
import secrets
import string
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

_verification_attempts: dict[str, list[float]] = defaultdict(list)
_VERIFICATION_RATE_WINDOW = 60.0
_VERIFICATION_MAX_ATTEMPTS = 6


@dataclass(frozen=True)
class LoginChallenge:
    email: str
    code: str
    expires_at: float


@dataclass(frozen=True)
class AuthPrincipal:
    owner_id: str
    auth_type: str


# Login challenges are intentionally in-memory; a service restart clears pending
# codes, while established session cookies continue to use the signed cookie.
_pending_challenges: dict[str, LoginChallenge] = {}


def _is_production() -> bool:
    return settings.RUN_ENVIRONMENT == "production"


def create_session_token(subject: str | None = None) -> str:
    payload: object
    if subject:
        payload = {"sub": normalize_email(subject), "auth_type": "cookie"}
    else:
        payload = "authenticated"
    return _serializer.dumps(payload)


def create_session_cookie(response: Response, subject: str | None = None) -> None:
    token = create_session_token(subject)
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


def _principal_from_cookie_token(token: str | None) -> AuthPrincipal | None:
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
    except (SignatureExpired, BadSignature):
        return None

    if isinstance(payload, dict):
        subject = payload.get("sub")
        if isinstance(subject, str) and subject.strip():
            return AuthPrincipal(
                owner_id=f"email:{normalize_email(subject)}",
                auth_type=str(payload.get("auth_type") or "cookie"),
            )
        return None

    # Preserve compatibility with old already-issued web cookies without making
    # them a shared global owner. The owner is scoped to this exact signed token.
    if payload == "authenticated":
        fingerprint = sha256(token.encode("utf-8")).hexdigest()[:16]
        return AuthPrincipal(owner_id=f"legacy_cookie:{fingerprint}", auth_type="legacy_cookie")
    return None


def _principal_from_api_key(key: str) -> AuthPrincipal:
    fingerprint = sha256(key.encode("utf-8")).hexdigest()[:16]
    return AuthPrincipal(owner_id=f"api_key:{fingerprint}", auth_type="api_key")


def get_auth_principal(request: Request) -> AuthPrincipal | None:
    principal = _principal_from_cookie_token(request.cookies.get(_SESSION_COOKIE))
    if principal is not None:
        return principal
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        if key == settings.HERMES_VOICE_API_KEY:
            return _principal_from_api_key(key)
    return None


def verify_session_ws(websocket: WebSocket) -> bool:
    token = websocket.cookies.get(_SESSION_COOKIE)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return True
    except (SignatureExpired, BadSignature):
        return False


def get_auth_principal_ws(websocket: WebSocket) -> AuthPrincipal | None:
    principal = _principal_from_cookie_token(websocket.cookies.get(_SESSION_COOKIE))
    if principal is not None:
        return principal
    auth_header = websocket.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        if key == settings.HERMES_VOICE_API_KEY:
            return _principal_from_api_key(key)
    return None


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


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_allowed_web_emails() -> set[str]:
    return {
        normalized
        for raw in settings.HERMES_VOICE_WEB_EMAILS.split(",")
        if (normalized := normalize_email(raw))
    }


def is_allowed_web_email(email: str) -> bool:
    return normalize_email(email) in get_allowed_web_emails()


def _check_bucket_rate_limit(
    bucket: dict[str, list[float]],
    key: str,
    *,
    window: float,
    max_attempts: int,
) -> tuple[bool, Optional[float]]:
    now = time.monotonic()
    window_start = now - window
    attempts = bucket[key]
    bucket[key] = [t for t in attempts if t > window_start]
    if len(bucket[key]) >= max_attempts:
        retry_after = bucket[key][0] + window - now
        return False, max(retry_after, 0.0)
    bucket[key].append(now)
    return True, None


def check_rate_limit(ip: str) -> tuple[bool, Optional[float]]:
    return _check_bucket_rate_limit(
        _login_attempts,
        ip,
        window=_LOGIN_RATE_WINDOW,
        max_attempts=_LOGIN_MAX_ATTEMPTS,
    )


def check_verification_rate_limit(key: str) -> tuple[bool, Optional[float]]:
    return _check_bucket_rate_limit(
        _verification_attempts,
        key,
        window=_VERIFICATION_RATE_WINDOW,
        max_attempts=_VERIFICATION_MAX_ATTEMPTS,
    )


def _generate_code() -> str:
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(settings.LOGIN_CODE_LENGTH))


def create_login_challenge(email: str, now: float | None = None) -> tuple[str, str]:
    now = time.monotonic() if now is None else now
    normalized_email = normalize_email(email)
    challenge_id = secrets.token_urlsafe(32)
    code = _generate_code()
    _pending_challenges[challenge_id] = LoginChallenge(
        email=normalized_email,
        code=code,
        expires_at=now + settings.LOGIN_CODE_TTL_SECONDS,
    )
    return challenge_id, code


def verify_login_challenge(
    challenge_id: str,
    code: str,
    now: float | None = None,
) -> bool:
    now = time.monotonic() if now is None else now
    challenge = _pending_challenges.get(challenge_id)
    if challenge is None:
        return False
    if challenge.expires_at < now:
        _pending_challenges.pop(challenge_id, None)
        return False
    if not hmac.compare_digest(challenge.code, code.strip()):
        return False
    _pending_challenges.pop(challenge_id, None)
    return True


def verify_login_challenge_subject(
    challenge_id: str,
    code: str,
    now: float | None = None,
) -> str | None:
    now = time.monotonic() if now is None else now
    challenge = _pending_challenges.get(challenge_id)
    if challenge is None:
        return None
    if challenge.expires_at < now:
        _pending_challenges.pop(challenge_id, None)
        return None
    if not hmac.compare_digest(challenge.code, code.strip()):
        return None
    _pending_challenges.pop(challenge_id, None)
    return challenge.email
