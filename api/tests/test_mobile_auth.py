from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_auth_state(monkeypatch):
    from app import auth
    from app.config import settings

    auth._login_attempts.clear()
    auth._verification_attempts.clear()
    auth._pending_challenges.clear()
    monkeypatch.setattr(settings, "HERMES_VOICE_WEB_EMAILS", "allowed@example.com")
    monkeypatch.setattr(settings, "HERMES_VOICE_WEB_PASSWORD", "test-password")


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_login_returns_challenge_id(client, monkeypatch):
    async def fake_send(email: str, code: str) -> None:
        pass

    monkeypatch.setattr("app.routes.mobile_auth.send_verification_code", fake_send)

    resp = await client.post(
        "/api/auth/login",
        json={"email": "allowed@example.com", "password": "test-password"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "challenge_id" in body
    assert isinstance(body["challenge_id"], str)
    assert len(body["challenge_id"]) > 8


@pytest.mark.asyncio
async def test_api_login_wrong_password_returns_401(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "allowed@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_api_login_disallowed_email_returns_401(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "stranger@example.com", "password": "test-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_login_email_send_failure_returns_502(client, monkeypatch):
    async def fail_send(email: str, code: str) -> None:
        raise RuntimeError("SMTP down")

    monkeypatch.setattr("app.routes.mobile_auth.send_verification_code", fail_send)

    resp = await client.post(
        "/api/auth/login",
        json={"email": "allowed@example.com", "password": "test-password"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "EMAIL_SEND_FAILED"


@pytest.mark.asyncio
async def test_api_login_mock_email_returns_code(client, monkeypatch):
    from app.config import settings

    async def fail_send(email: str, code: str) -> None:
        raise AssertionError("mock email mode should not send SMTP email")

    monkeypatch.setattr(settings, "HERMES_VOICE_MOCK_EMAIL", True)
    monkeypatch.setattr("app.routes.mobile_auth.send_verification_code", fail_send)

    resp = await client.post(
        "/api/auth/login",
        json={"email": "allowed@example.com", "password": "test-password"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "challenge_id" in body
    assert body["mock_code"].isdigit()
    assert len(body["mock_code"]) == settings.LOGIN_CODE_LENGTH

    verify_resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": body["challenge_id"], "code": body["mock_code"]},
    )
    assert verify_resp.status_code == 200
    assert "hv_session" in verify_resp.cookies


# ---------------------------------------------------------------------------
# POST /api/auth/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_verify_success_sets_session_cookie(client, monkeypatch):
    async def fake_send(email: str, code: str) -> None:
        pass

    monkeypatch.setattr("app.routes.mobile_auth.send_verification_code", fake_send)

    from app import auth

    challenge_id, code = auth.create_login_challenge("allowed@example.com")

    resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "hv_session" in resp.cookies


@pytest.mark.asyncio
async def test_api_verify_invalid_code_returns_401(client):
    from app import auth

    challenge_id, _ = auth.create_login_challenge("allowed@example.com")

    resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": challenge_id, "code": "000000"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CODE"


@pytest.mark.asyncio
async def test_api_verify_unknown_challenge_returns_401(client):
    resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": "no-such-id", "code": "123456"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/auth/session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_session_unauthenticated(client):
    resp = await client.get("/api/auth/session")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


@pytest.mark.asyncio
async def test_api_session_authenticated_after_verify(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.mobile_auth.send_verification_code",
        lambda *_: None,
    )
    from app import auth

    challenge_id, code = auth.create_login_challenge("allowed@example.com")
    verify_resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert verify_resp.status_code == 200

    # Re-use cookie from verify response
    session_resp = await client.get("/api/auth/session", cookies=verify_resp.cookies)
    assert session_resp.json() == {"authenticated": True}


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_logout_clears_session(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.mobile_auth.send_verification_code",
        lambda *_: None,
    )
    from app import auth

    challenge_id, code = auth.create_login_challenge("allowed@example.com")
    verify_resp = await client.post(
        "/api/auth/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert verify_resp.status_code == 200

    logout_resp = await client.post("/api/auth/logout", cookies=verify_resp.cookies)
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"ok": True}

    # Session should now be invalid
    session_resp = await client.get(
        "/api/auth/session", cookies=logout_resp.cookies
    )
    assert session_resp.json() == {"authenticated": False}
