from __future__ import annotations

import os

# Set env vars before any app imports so config loads correctly
os.environ.setdefault("NAME_APP", "hermes_voice_api_test")
os.environ.setdefault("RUN_ENVIRONMENT", "development")
os.environ.setdefault("HERMES_VOICE_WEB_PASSWORD", "test-password")
os.environ.setdefault("HERMES_VOICE_API_KEY", "test-api-key")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-chars-long")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("HERMES_BASE_URL", "http://127.0.0.1:8642/v1")
os.environ.setdefault("HERMES_API_KEY", "test")
os.environ.setdefault("HERMES_MODEL", "hermes-agent")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
