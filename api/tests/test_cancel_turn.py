from __future__ import annotations

import json
import pytest

pytestmark = pytest.mark.asyncio


async def test_cancel_turn_no_active_task_returns_idle(client):
    """cancel_turn with no running pipeline → active_state=idle + turn_end, no error."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "cancel_turn"}))

            msg1 = ws.receive_json()
            msg2 = ws.receive_json()

            frames = [msg1, msg2]
            events = {m.get("event") for m in frames}

            assert "active_state" in events
            assert "turn_end" in events

            idle_frames = [m for m in frames if m.get("event") == "active_state"]
            assert any(f.get("state") == "idle" for f in idle_frames)

            error_frames = [m for m in frames if m.get("event") == "error"]
            assert error_frames == [], f"unexpected error frame(s): {error_frames}"


async def test_cancel_turn_connection_stays_open(client):
    """After cancel_turn, connection is still usable (new_session works)."""
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/voice", headers={"Authorization": "Bearer test-api-key"}) as ws:
            ws.receive_json()  # session_started

            ws.send_text(json.dumps({"event": "cancel_turn"}))
            ws.receive_json()  # active_state=idle
            ws.receive_json()  # turn_end

            ws.send_text(json.dumps({"event": "new_session"}))
            msg = ws.receive_json()
            assert msg["event"] == "session_started"
