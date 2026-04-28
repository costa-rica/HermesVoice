from __future__ import annotations

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from ..config import settings

router = APIRouter()


@router.get("/health/live")
async def liveness() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    all_ok = True

    # Check OpenAI key presence
    if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-placeholder"):
        checks["openai_key"] = "present"
    else:
        checks["openai_key"] = "missing or placeholder"
        all_ok = False

    # Check Hermes loopback reachability
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                settings.HERMES_BASE_URL.rstrip("/").replace("/v1", "") + "/health",
                headers={"Authorization": f"Bearer {settings.HERMES_API_KEY}"},
            )
        if resp.status_code < 500:
            checks["hermes"] = "reachable"
        else:
            checks["hermes"] = f"http_{resp.status_code}"
            all_ok = False
    except Exception as exc:
        logger.debug(f"Hermes health check failed: {exc}")
        checks["hermes"] = "unreachable"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse({"status": "ok" if all_ok else "degraded", "checks": checks}, status_code=status_code)
