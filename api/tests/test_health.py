from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_liveness(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness_returns_json(client):
    resp = await client.get("/health/ready")
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert "openai_key" in data["checks"]
    assert "hermes" in data["checks"]
