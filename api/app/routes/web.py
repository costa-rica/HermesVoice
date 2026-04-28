from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from ..auth import (
    check_rate_limit,
    clear_session_cookie,
    create_session_cookie,
    verify_session,
)
from ..config import settings
from ..errors import error_response

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
)

_LOGIN_PAGE_TMPL = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<title>HermesVoice - Login</title>"
    "<style>" + _LOGIN_CSS + "</style></head><body>"
    "<form method=post action=/login>"
    "<h2 style=margin:0>HermesVoice</h2>"
    "<!--ERROR_HTML-->"
    "<input type=password name=password placeholder=Password autofocus required>"
    "<button type=submit>Sign in</button>"
    "</form></body></html>"
)


def _login_page(error: str = "") -> str:
    return _LOGIN_PAGE_TMPL.replace("<!--ERROR_HTML-->", error)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if verify_session(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_login_page())


@router.post("/login")
async def login(
    request: Request,
    response: Response,
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

    if password != settings.HERMES_VOICE_WEB_PASSWORD:
        logger.warning(f"Failed login attempt from {ip}")
        html = _login_page('<p class="err">Incorrect password.</p>')
        return HTMLResponse(html, status_code=401)

    logger.info(f"Successful login from {ip}")
    redirect = RedirectResponse("/", status_code=302)
    create_session_cookie(redirect)
    return redirect


@router.post("/logout")
async def logout(response: Response) -> Response:
    redirect = RedirectResponse("/login", status_code=302)
    clear_session_cookie(redirect)
    return redirect
