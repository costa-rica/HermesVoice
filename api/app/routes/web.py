from __future__ import annotations

from html import escape

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from ..auth import (
    check_rate_limit,
    check_verification_rate_limit,
    clear_session_cookie,
    create_session_cookie,
    create_login_challenge,
    is_allowed_web_email,
    normalize_email,
    verify_login_challenge,
    verify_session,
)
from ..config import settings
from ..errors import error_response
from ..services.email import send_verification_code

router = APIRouter()

_LOGIN_CSS = (
    "body{font-family:system-ui,sans-serif;display:flex;justify-content:center;"
    "align-items:center;height:100vh;margin:0;background:#111;color:#eee}"
    "form{display:flex;flex-direction:column;gap:12px;width:280px}"
    "input{padding:10px;border-radius:6px;border:1px solid #444;background:#222;"
    "color:#eee;font-size:1rem}"
    "button{padding:10px;border-radius:6px;border:none;background:#4f8ef7;"
    "color:#fff;font-size:1rem;cursor:pointer}"
    ".err{color:#f87;font-size:.9rem}"
    ".hint{color:#aaa;font-size:.9rem;line-height:1.35}"
)

_LOGIN_PAGE_TMPL = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<title>HermesVoice - Login</title>"
    "<style>" + _LOGIN_CSS + "</style></head><body>"
    "<form method=post action=/login>"
    "<h2 style=margin:0>HermesVoice</h2>"
    "<!--ERROR_HTML-->"
    "<input type=email name=email placeholder=Email autocomplete=email autofocus required>"
    "<input type=password name=password placeholder=Password required>"
    "<button type=submit>Sign in</button>"
    "</form></body></html>"
)

_VERIFY_PAGE_TMPL = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<title>HermesVoice - Verify</title>"
    "<style>" + _LOGIN_CSS + "</style></head><body>"
    "<form method=post action=/login/verify>"
    "<h2 style=margin:0>Check your email</h2>"
    "<p class=hint>Enter the verification code sent to <!--EMAIL-->.</p>"
    "<!--ERROR_HTML-->"
    '<input name=challenge_id type=hidden value="<!--CHALLENGE_ID-->">'
    "<input type=text name=code placeholder=Code inputmode=numeric "
    "autocomplete=one-time-code pattern='[0-9]*' autofocus required>"
    "<button type=submit>Verify</button>"
    "</form></body></html>"
)


def _login_page(error: str = "") -> str:
    return _LOGIN_PAGE_TMPL.replace("<!--ERROR_HTML-->", error)


def _verify_page(challenge_id: str, email: str, error: str = "") -> str:
    return (
        _VERIFY_PAGE_TMPL.replace("<!--ERROR_HTML-->", error)
        .replace("<!--CHALLENGE_ID-->", escape(challenge_id, quote=True))
        .replace("<!--EMAIL-->", escape(email))
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if verify_session(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_login_page())


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = check_rate_limit(ip)
    if not allowed:
        logger.warning(f"Login rate limit hit for IP {ip}")
        return error_response(
            "RATE_LIMIT_EXCEEDED",
            "Too many login attempts. Try again later.",
            429,
            details=f"Retry after {retry_after:.0f} seconds",
        )

    normalized_email = normalize_email(email)
    if (
        password != settings.HERMES_VOICE_WEB_PASSWORD
        or not is_allowed_web_email(normalized_email)
    ):
        logger.warning(f"Failed login attempt from {ip}")
        html = _login_page('<p class="err">Incorrect email or password.</p>')
        return HTMLResponse(html, status_code=401)

    challenge_id, code = create_login_challenge(normalized_email)
    try:
        await send_verification_code(normalized_email, code)
    except Exception:
        logger.exception(f"Failed to send login verification code to {normalized_email}")
        return error_response(
            "EMAIL_SEND_FAILED",
            "Unable to send verification code. Try again later.",
            502,
        )

    logger.info(f"Started 2FA login challenge for {normalized_email} from {ip}")
    return HTMLResponse(_verify_page(challenge_id, normalized_email))


@router.post("/login/verify")
async def verify_login(
    request: Request,
    challenge_id: str = Form(...),
    code: str = Form(...),
) -> Response:
    ip = request.client.host if request.client else "unknown"
    rate_key = f"{ip}:{challenge_id}"
    allowed, retry_after = check_verification_rate_limit(rate_key)
    if not allowed:
        logger.warning(f"Verification rate limit hit for IP {ip}")
        return error_response(
            "RATE_LIMIT_EXCEEDED",
            "Too many verification attempts. Try again later.",
            429,
            details=f"Retry after {retry_after:.0f} seconds",
        )

    if not verify_login_challenge(challenge_id, code):
        html = _verify_page(
            challenge_id,
            "your allowed address",
            '<p class="err">Invalid or expired code.</p>',
        )
        return HTMLResponse(html, status_code=401)

    logger.info(f"Successful 2FA login from {ip}")
    redirect = RedirectResponse("/", status_code=302)
    create_session_cookie(redirect)
    return redirect


@router.post("/logout")
async def logout(response: Response) -> Response:
    redirect = RedirectResponse("/login", status_code=302)
    clear_session_cookie(redirect)
    return redirect
