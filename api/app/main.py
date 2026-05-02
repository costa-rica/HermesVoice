from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .auth import verify_session
from .config import settings
from .logging_config import configure_logging
from .routes import health, mobile_auth, voice, web
from .services.voice_store import ensure_schema

configure_logging(
    name_app=settings.NAME_APP,
    run_environment=settings.RUN_ENVIRONMENT,
    path_to_logs=settings.PATH_TO_LOGS,
)

WEB_DIST = Path(__file__).parent.parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"HermesVoice starting — env={settings.RUN_ENVIRONMENT!r} "
        f"app={settings.NAME_APP!r}"
    )
    ensure_schema()
    yield
    logger.info("HermesVoice shutting down")


app = FastAPI(title="HermesVoice API", lifespan=lifespan)

_ALLOWED_ORIGINS = (
    ["https://hermes-voice.dashanddata.com"]
    if settings.RUN_ENVIRONMENT == "production"
    else ["http://localhost:5173", "http://localhost:8700", "http://127.0.0.1:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(mobile_auth.router)
app.include_router(web.router)
app.include_router(voice.router)

# Serve built web app if it exists
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index(request: Request):
        if not verify_session(request):
            return RedirectResponse("/login", status_code=302)
        index = WEB_DIST / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        return HTMLResponse("<h1>HermesVoice</h1><p>Web app not built yet.</p>")

else:

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        if not verify_session(request):
            return RedirectResponse("/login", status_code=302)
        return HTMLResponse(
            "<h1>HermesVoice</h1>"
            "<p>Web client not built yet. Run <code>cd web && npm run build</code>.</p>"
            '<p><a href="/health/live">Health</a></p>'
            '<form method="post" action="/logout">'
            '<button>Logout</button></form>'
        )
