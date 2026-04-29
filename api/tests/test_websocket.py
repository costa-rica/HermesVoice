from __future__ import annotations

import json
import pytest
from httpx import ASGITransport, AsyncClient


pytestmark = pytest.mark.asyncio


async def _get_session_cookie(client) -> str:
    resp = await client.post("/login", data={"password": "test-password"}, follow_redirects=False)
    assert resp.status_code == 302
    return resp.cookies.get("hv_session", "")


async def test_ws_rejects_unauthenticated(client):
    """WebSocket closes with error frame if no session cookie."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "error"
            assert msg["error"]["code"] == "AUTH_FAILED"


async def test_ws_authenticates_with_api_key(client):
    """WebSocket accepts API key auth and sends session_started."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
            assert "conversation_id" in msg


async def test_ws_session_started_on_connect(client):
    """Authenticated WS sends session_started with conversation_id."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
            cid = msg["conversation_id"]
            assert len(cid) == 36  # UUID


async def test_ws_binary_before_start_utterance_rejected(client):
    """Binary audio before start_utterance gets PROTOCOL_ERROR."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.receive_json()  # session_started
            ws.send_bytes(b"\x00\x01\x02")
            msg = ws.receive_json()
            assert msg["event"] == "error"
            assert msg["error"]["code"] == "PROTOCOL_ERROR"


async def test_ws_unsupported_format_rejected(client):
    """start_utterance with bad format gets UNSUPPORTED_FORMAT error."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.receive_json()  # session_started
            ws.send_text(json.dumps({
                "event": "start_utterance",
                "format": "mp3",
                "sample_rate": 44100,
            }))
            msg = ws.receive_json()
            assert msg["event"] == "error"
            assert msg["error"]["code"] == "UNSUPPORTED_FORMAT"


async def test_ws_new_session_creates_new_conversation(client):
    """new_session event creates new conversation_id and sends session_started."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            first = ws.receive_json()
            assert first["event"] == "session_started"
            old_cid = first["conversation_id"]

            ws.send_text(json.dumps({"event": "new_session"}))
            second = ws.receive_json()
            assert second["event"] == "session_started"
            new_cid = second["conversation_id"]
            assert new_cid != old_cid


async def test_ws_unknown_event_ignored(client):
    """Unknown JSON event frames should not cause errors."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect(
            "/ws/voice", headers={"Authorization": "Bearer test-api-key"}
        ) as ws:
            ws.receive_json()  # session_started
            ws.send_text(json.dumps({"event": "future_unknown_event", "data": "anything"}))
            # No error frame should follow; connection stays open
            # Send new_session to verify socket is still responsive
            ws.send_text(json.dumps({"event": "new_session"}))
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
