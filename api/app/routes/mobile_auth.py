from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from ..auth import (
    check_rate_limit,
    check_verification_rate_limit,
    clear_session_cookie,
    create_login_challenge,
    create_session_cookie,
    is_allowed_web_email,
    normalize_email,
    verify_login_challenge,
    verify_session,
)
from ..config import settings
from ..errors import error_response
from ..services.email import send_verification_code

router = APIRouter(prefix="/api/auth", tags=["mobile-auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyRequest(BaseModel):
    challenge_id: str
    code: str


@router.post("/login")
async def api_login(body: LoginRequest, request: Request) -> JSONResponse:
    """Step 1 of 2FA: validate email+password, send a verification code."""
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = check_rate_limit(ip)
    if not allowed:
        logger.warning(f"[mobile] Login rate limit for IP {ip}")
        return error_response(
            "RATE_LIMIT_EXCEEDED",
            "Too many login attempts. Try again later.",
            429,
            details=f"Retry after {retry_after:.0f} seconds",
        )

    normalized = normalize_email(body.email)
    if (
        body.password != settings.HERMES_VOICE_WEB_PASSWORD
        or not is_allowed_web_email(normalized)
    ):
        logger.warning(f"[mobile] Failed login from {ip}")
        return error_response("INVALID_CREDENTIALS", "Incorrect email or password.", 401)

    challenge_id, code = create_login_challenge(normalized)
    if settings.HERMES_VOICE_MOCK_EMAIL:
        logger.info("[mobile] mock email mode enabled; returning verification code")
        return JSONResponse({"challenge_id": challenge_id, "mock_code": code})
    else:
        try:
            await send_verification_code(normalized, code)
        except Exception:
            logger.exception(f"[mobile] Email send failed for {normalized}")
            return error_response(
                "EMAIL_SEND_FAILED",
                "Unable to send verification code. Try again later.",
                502,
            )

    logger.info(f"[mobile] 2FA challenge started for {normalized} from {ip}")
    return JSONResponse({"challenge_id": challenge_id})


@router.post("/verify")
async def api_verify(body: VerifyRequest, request: Request) -> JSONResponse:
    """Step 2 of 2FA: validate the emailed code and issue a session cookie."""
    ip = request.client.host if request.client else "unknown"
    rate_key = f"{ip}:{body.challenge_id}"
    allowed, retry_after = check_verification_rate_limit(rate_key)
    if not allowed:
        return error_response(
            "RATE_LIMIT_EXCEEDED",
            "Too many verification attempts. Try again later.",
            429,
            details=f"Retry after {retry_after:.0f} seconds",
        )

    if not verify_login_challenge(body.challenge_id, body.code):
        return error_response("INVALID_CODE", "Invalid or expired code.", 401)

    logger.info(f"[mobile] Successful 2FA login from {ip}")
    resp = JSONResponse({"ok": True})
    create_session_cookie(resp)
    return resp


@router.get("/session")
async def api_session(request: Request) -> JSONResponse:
    """Non-destructive session check; returns whether the caller is authenticated."""
    return JSONResponse({"authenticated": verify_session(request)})


@router.post("/logout")
async def api_logout() -> JSONResponse:
    """Clear the session cookie."""
    resp = JSONResponse({"ok": True})
    clear_session_cookie(resp)
    return resp
