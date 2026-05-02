from __future__ import annotations

import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


def _cookie(email: str) -> dict[str, str]:
    from app.auth import create_session_token

    return {"hv_session": create_session_token(email)}


def _cookie_header(email: str) -> dict[str, str]:
    return {"Cookie": f"hv_session={_cookie(email)['hv_session']}"}


def _test_client():
    from app.main import app
    from starlette.testclient import TestClient

    return TestClient(app)


async def test_session_crud_for_authenticated_owner(client):
    headers = _cookie_header("allowed@example.com")

    created = await client.post(
        "/api/voice/sessions",
        json={"title": "Trip planning"},
        headers=headers,
    )
    assert created.status_code == 201
    session = created.json()["session"]
    assert session["title"] == "Trip planning"
    assert session["conversation_id"] == session["hermes_conversation_id"]
    assert session["message_count"] == 0
    assert session["archived_at"] is None

    listed = await client.get("/api/voice/sessions", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["sessions"]] == [session["id"]]

    fetched = await client.get(f"/api/voice/sessions/{session['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["session"]["id"] == session["id"]

    patched = await client.patch(
        f"/api/voice/sessions/{session['id']}",
        json={"title": "Flights and hotels"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["session"]["title"] == "Flights and hotels"

    deleted = await client.delete(f"/api/voice/sessions/{session['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["archived_at"] is not None

    listed_after_delete = await client.get("/api/voice/sessions", headers=headers)
    assert listed_after_delete.json()["sessions"] == []


async def test_sessions_and_messages_reject_another_owner(client):
    from app.services import voice_store

    owner_a = _cookie_header("owner-a@example.com")
    owner_b = _cookie_header("owner-b@example.com")

    created = await client.post(
        "/api/voice/sessions",
        json={"title": "Private"},
        headers=owner_a,
    )
    session_id = created.json()["session"]["id"]
    voice_store.add_message(
        "email:owner-a@example.com",
        session_id,
        turn_id="1",
        role="user",
        text="private transcript",
    )

    session_resp = await client.get(f"/api/voice/sessions/{session_id}", headers=owner_b)
    assert session_resp.status_code == 403
    assert session_resp.json()["error"]["code"] == "VOICE_SESSION_FORBIDDEN"

    messages_resp = await client.get(
        f"/api/voice/sessions/{session_id}/messages",
        headers=owner_b,
    )
    assert messages_resp.status_code == 403
    assert messages_resp.json()["error"]["code"] == "VOICE_SESSION_FORBIDDEN"


async def test_websocket_without_session_id_creates_persistent_session(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            started = ws.receive_json()
            assert started["event"] == "session_started"
            assert started["session_id"]
            assert started["conversation_id"] == started["session_id"]
            assert started["resumed"] is False
            assert started["created"] is True


async def test_websocket_existing_web_path_without_client_hello_still_works(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            started = ws.receive_json()
            assert started["event"] == "session_started"
            assert "conversation_id" in started
            assert "downlink_format" in started
            assert "session_id" in started


async def test_websocket_with_valid_session_id_resumes(client):
    from app.services import voice_store

    owner = "api_key:4c806362b613f749"
    session = voice_store.create_session(owner, title="Resume me")

    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "accepted_downlink_formats": ["wav_pcm16"],
                "session_id": session["id"],
            }))
            started = ws.receive_json()
            assert started["session_id"] == session["id"]
            assert started["conversation_id"] == session["conversation_id"]
            assert started["resumed"] is True
            assert started["created"] is False


async def test_websocket_invalid_and_not_owned_session_id_errors(client):
    from app.services import voice_store

    owned_by_cookie = voice_store.create_session("email:other@example.com")

    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "accepted_downlink_formats": ["wav_pcm16"],
                "session_id": "00000000-0000-0000-0000-000000000000",
            }))
            missing = ws.receive_json()
            assert missing["event"] == "error"
            assert missing["error"]["code"] == "VOICE_SESSION_NOT_FOUND"

        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "accepted_downlink_formats": ["wav_pcm16"],
                "session_id": owned_by_cookie["id"],
            }))
            forbidden = ws.receive_json()
            assert forbidden["event"] == "error"
            assert forbidden["error"]["code"] == "VOICE_SESSION_FORBIDDEN"


async def test_new_session_creates_new_persistent_session(client):
    with _test_client() as tc:
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            first = ws.receive_json()
            ws.send_text(json.dumps({"event": "new_session"}))
            second = ws.receive_json()
            assert second["event"] == "session_started"
            assert second["session_id"] != first["session_id"]
            assert second["conversation_id"] != first["conversation_id"]
            assert second["resumed"] is False
            assert second["created"] is True


async def test_resumed_session_passes_stable_conversation_id_to_pipeline(client):
    from app.services import voice_store

    owner = "api_key:4c806362b613f749"
    session = voice_store.create_session(owner)
    captured: list[str] = []

    async def fake_turn(**kwargs):
        captured.append(kwargs["conversation_id"])
        await kwargs["send_json"]({"event": "turn_end", "turn_id": str(kwargs["turn_id"])})

    with _test_client() as tc, patch("app.routes.voice.run_voice_turn", fake_turn):
        with tc.websocket_connect(
            "/ws/voice",
            headers={"Authorization": "Bearer test-api-key"},
        ) as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "accepted_downlink_formats": ["wav_pcm16"],
                "session_id": session["id"],
            }))
            ws.receive_json()
            ws.send_text(json.dumps({
                "event": "start_utterance",
                "format": "wav",
                "sample_rate": 16000,
            }))
            ws.send_bytes(b"\x00" * 100)
            ws.send_text(json.dumps({"event": "end_of_utterance"}))
            assert ws.receive_json()["event"] == "turn_end"

    assert captured == [session["conversation_id"]]


async def test_stored_transcript_and_assistant_messages_survive_reconnect(client):
    session_id_holder: dict[str, str] = {}

    async def fake_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        await kwargs["send_json"]({"event": "transcript", "text": "hello", "turn_id": turn_id})
        await kwargs["send_json"]({
            "event": "assistant_text",
            "text": "hi there",
            "final": True,
            "turn_id": turn_id,
        })
        await kwargs["send_json"]({"event": "turn_end", "turn_id": turn_id})

    with _test_client() as tc, patch("app.routes.voice.run_voice_turn", fake_turn):
        tc.cookies.set("hv_session", _cookie("allowed@example.com")["hv_session"])
        with tc.websocket_connect("/ws/voice") as ws:
            started = ws.receive_json()
            session_id_holder["id"] = started["session_id"]
            ws.send_text(json.dumps({
                "event": "start_utterance",
                "format": "wav",
                "sample_rate": 16000,
            }))
            ws.send_bytes(b"\x00" * 100)
            ws.send_text(json.dumps({"event": "end_of_utterance"}))
            frames = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            assert [frame["event"] for frame in frames] == [
                "transcript",
                "assistant_text",
                "turn_end",
            ]

        with tc.websocket_connect("/ws/voice") as ws:
            ws.send_text(json.dumps({
                "event": "client_hello",
                "accepted_downlink_formats": ["wav_pcm16"],
                "session_id": session_id_holder["id"],
            }))
            resumed = ws.receive_json()
            assert resumed["resumed"] is True

        messages = tc.get(f"/api/voice/sessions/{session_id_holder['id']}/messages")
        assert messages.status_code == 200
        assert [(m["role"], m["text"]) for m in messages.json()["messages"]] == [
            ("user", "hello"),
            ("assistant", "hi there"),
        ]
