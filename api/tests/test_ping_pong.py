from __future__ import annotations

import json
import pytest

pytestmark = pytest.mark.asyncio


async def test_ping_returns_pong(client):
    """Sending ping → pong response."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "ping"}))
            msg = ws.receive_json()
            assert msg["event"] == "pong"


async def test_ping_echoes_id(client):
    """Ping with id field → pong echoes the same id."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "ping", "id": "hb-42"}))
            msg = ws.receive_json()
            assert msg["event"] == "pong"
            assert msg.get("id") == "hb-42"


async def test_ping_without_id_no_id_in_pong(client):
    """Ping without id → pong has no id field."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "ping"}))
            msg = ws.receive_json()
            assert msg["event"] == "pong"
            assert "id" not in msg


async def test_ping_connection_stays_open(client):
    """After ping/pong, connection remains usable."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "ping", "id": "liveness-1"}))
            ws.receive_json()  # pong

            ws.send_text(json.dumps({"event": "new_session"}))
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
