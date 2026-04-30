from __future__ import annotations

import re

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


@pytest.mark.asyncio
async def test_root_redirects_to_login_when_unauthenticated(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_returns_html(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert b"HermesVoice" in resp.content
    assert b"name=email" in resp.content
    assert b"name=password" in resp.content


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_disallows_unlisted_email(client, monkeypatch):
    send_calls = []

    async def fake_send(email: str, code: str) -> None:
        send_calls.append((email, code))

    monkeypatch.setattr("app.routes.web.send_verification_code", fake_send)

    resp = await client.post(
        "/login",
        data={"email": "blocked@example.com", "password": "test-password"},
    )

    assert resp.status_code == 401
    assert "hv_session" not in resp.cookies
    assert send_calls == []


@pytest.mark.asyncio
async def test_login_correct_email_and_password_sends_code_without_session(
    client,
    monkeypatch,
):
    send_calls = []

    async def fake_send(email: str, code: str) -> None:
        send_calls.append((email, code))

    monkeypatch.setattr("app.routes.web.send_verification_code", fake_send)

    resp = await client.post(
        "/login",
        data={"email": "Allowed@Example.com", "password": "test-password"},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert "hv_session" not in resp.cookies
    assert send_calls == [("allowed@example.com", send_calls[0][1])]
    assert re.fullmatch(r"\d{6}", send_calls[0][1])
    assert b"name=challenge_id" in resp.content
    assert b"name=code" in resp.content


@pytest.mark.asyncio
async def test_verify_code_sets_cookie_and_redirects(client, monkeypatch):
    sent_codes = {}

    async def fake_send(email: str, code: str) -> None:
        sent_codes[email] = code

    monkeypatch.setattr("app.routes.web.send_verification_code", fake_send)

    login_resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "test-password"},
    )
    challenge_id = re.search(
        rb'name=challenge_id type=hidden value="([^"]+)"',
        login_resp.content,
    ).group(1).decode("utf-8")

    resp = await client.post(
        "/login/verify",
        data={"challenge_id": challenge_id, "code": sent_codes["allowed@example.com"]},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    assert "hv_session" in resp.cookies


@pytest.mark.asyncio
async def test_verify_wrong_code_fails(client, monkeypatch):
    async def fake_send(email: str, code: str) -> None:
        pass

    monkeypatch.setattr("app.routes.web.send_verification_code", fake_send)

    login_resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "test-password"},
    )
    challenge_id = re.search(
        rb'name=challenge_id type=hidden value="([^"]+)"',
        login_resp.content,
    ).group(1).decode("utf-8")

    resp = await client.post(
        "/login/verify",
        data={"challenge_id": challenge_id, "code": "000000"},
    )

    assert resp.status_code == 401
    assert "hv_session" not in resp.cookies


@pytest.mark.asyncio
async def test_verify_used_code_cannot_be_reused(client, monkeypatch):
    sent_codes = {}

    async def fake_send(email: str, code: str) -> None:
        sent_codes[email] = code

    monkeypatch.setattr("app.routes.web.send_verification_code", fake_send)

    login_resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "test-password"},
    )
    challenge_id = re.search(
        rb'name=challenge_id type=hidden value="([^"]+)"',
        login_resp.content,
    ).group(1).decode("utf-8")

    first = await client.post(
        "/login/verify",
        data={"challenge_id": challenge_id, "code": sent_codes["allowed@example.com"]},
    )
    second = await client.post(
        "/login/verify",
        data={"challenge_id": challenge_id, "code": sent_codes["allowed@example.com"]},
    )

    assert first.status_code == 302
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limit(client):
    # Exhaust the 5-attempt rate limit
    for _ in range(5):
        await client.post(
            "/login",
            data={"email": "allowed@example.com", "password": "wrong"},
        )
    resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "wrong"},
    )
    assert resp.status_code == 429
    data = resp.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_error_response_shape(client):
    """Verify standard error shape: error.code, error.message, error.status."""
    # Reset rate limit state by using a fresh unique IP via headers isn't trivial,
    # so test the shape from login rate limit directly
    for _ in range(5):
        await client.post(
            "/login",
            data={"email": "allowed@example.com", "password": "wrong"},
        )
    resp = await client.post(
        "/login",
        data={"email": "allowed@example.com", "password": "wrong"},
    )
    assert resp.status_code == 429
    body = resp.json()
    err = body["error"]
    assert "code" in err
    assert "message" in err
    assert "status" in err
    assert err["status"] == 429


def test_allowed_web_email_parsing_is_trimmed_case_insensitive(monkeypatch):
    from app import auth
    from app.config import settings

    monkeypatch.setattr(
        settings,
        "HERMES_VOICE_WEB_EMAILS",
        " ALLOWED@example.com, second@example.com, ,",
    )

    assert auth.get_allowed_web_emails() == {
        "allowed@example.com",
        "second@example.com",
    }
    assert auth.normalize_email(" Allowed@Example.COM ") == "allowed@example.com"
    assert auth.is_allowed_web_email("SECOND@example.com")
    assert not auth.is_allowed_web_email("blocked@example.com")


def test_expired_login_challenge_fails(monkeypatch):
    from app import auth
    from app.config import settings

    monkeypatch.setattr(settings, "LOGIN_CODE_TTL_SECONDS", 600)
    challenge_id, code = auth.create_login_challenge(
        "allowed@example.com",
        now=1_000.0,
    )

    assert not auth.verify_login_challenge(
        challenge_id,
        code,
        now=1_601.0,
    )
