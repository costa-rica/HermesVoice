from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(
    code: str,
    message: str,
    status: int,
    details: str | None = None,
) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message, "status": status}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def ws_error_frame(code: str, message: str, status: int) -> dict:
    return {"event": "error", "error": {"code": code, "message": message, "status": status}}
