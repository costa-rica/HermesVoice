from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_root_redirects_to_login_when_unauthenticated(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


async def test_login_page_returns_html(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert b"HermesVoice" in resp.content


async def test_login_wrong_password_returns_401(client):
    resp = await client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 401


async def test_login_correct_password_sets_cookie_and_redirects(client):
    resp = await client.post("/login", data={"password": "test-password"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "hv_session" in resp.cookies


async def test_login_rate_limit(client):
    # Exhaust the 5-attempt rate limit
    for _ in range(5):
        await client.post("/login", data={"password": "wrong"})
    resp = await client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 429
    data = resp.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"


async def test_error_response_shape(client):
    """Verify standard error shape: error.code, error.message, error.status."""
    # Reset rate limit state by using a fresh unique IP via headers isn't trivial,
    # so test the shape from login rate limit directly
    for _ in range(5):
        await client.post("/login", data={"password": "wrong"})
    resp = await client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 429
    body = resp.json()
    err = body["error"]
    assert "code" in err
    assert "message" in err
    assert "status" in err
    assert err["status"] == 429
