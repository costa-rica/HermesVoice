# HermesVoice persistent sessions API handoff

Date: 2026-05-02
Branch: `dev_05_persistence`
Status: implemented and tested on the backend/API side.

## Summary

The backend now persists resumable voice sessions and finalized text messages. A stable persistent voice session owns the Hermes conversation id used by the voice pipeline. On reconnect, the server reuses the session's `conversation_id` when calling Hermes, so continuity comes from Hermes' native `conversation` field rather than replaying stored mobile messages.

Existing web behavior remains additive-compatible: web clients may still omit `client_hello`, and `session_started.conversation_id`, downlink format, sample rate, and channel fields remain present.

## Files Changed

- `api/app/auth.py`
- `api/app/config.py`
- `api/app/main.py`
- `api/app/routes/mobile_auth.py`
- `api/app/routes/voice.py`
- `api/app/routes/web.py`
- `api/app/services/voice_store.py`
- `api/tests/conftest.py`
- `api/tests/test_voice_sessions.py`
- `docs/20260502_HERMES_VOICE_PERSISTENT_SESSIONS_API_HANDOFF.md`
- `docs/20260502_HERMES_VOICE_PERSISTENT_SESSIONS_MOBILE_HANDOFF_DRAFT.md`
- `docs/PROTOCOL.md`

## Storage And Setup

Storage uses SQLite via the Python standard library. Configure the database path with:

```bash
export HERMES_VOICE_DB_PATH=/path/to/hermes_voice_sessions.sqlite3
```

If unset, the backend defaults to:

```text
/tmp/hermes_voice_sessions.sqlite3
```

The schema is created automatically on FastAPI startup and lazily before store operations. No separate migration command is required for this V1.

Tables:

- `voice_sessions`: `id`, `owner_id`, `title`, `created_at`, `updated_at`, `last_message_preview`, `message_count`, `hermes_conversation_id`, `archived_at`
- `voice_messages`: `id`, `owner_id`, `session_id`, `turn_id`, `role`, `text`, `final`, `created_at`, `metadata`

## Auth And Ownership

All HTTP session/message endpoints require an auth principal. New email/password/2FA logins now mint `hv_session` cookies containing the normalized email subject. Voice records are scoped to that owner.

Mobile should use the normal `/api/auth/login` then `/api/auth/verify` cookie flow. Do not embed the bearer API key in the mobile app.

The existing bearer API-key WebSocket fallback still works for dev/service compatibility. When it creates or resumes sessions, it is scoped to a synthetic owner derived from the configured API key fingerprint, not a global mobile user.

Legacy already-issued cookies that only contain the old `"authenticated"` payload are still accepted for WebSocket compatibility and are scoped to a synthetic owner derived from that exact signed cookie token.

## HTTP API

All responses are JSON. Errors use the existing envelope:

```json
{
  "error": {
    "code": "VOICE_SESSION_NOT_FOUND",
    "message": "Voice session not found",
    "status": 404
  }
}
```

### List sessions

`GET /api/voice/sessions`

Response `200`:

```json
{
  "sessions": [
    {
      "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "title": "Trip planning",
      "created_at": "2026-05-02T18:10:20.000Z",
      "updated_at": "2026-05-02T18:14:03.000Z",
      "last_message_preview": "Let's compare those flight options.",
      "message_count": 6,
      "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "hermes_conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "archived_at": null
    }
  ]
}
```

Default ordering is newest `updated_at` first. Archived sessions are omitted from the list.

### Create session

`POST /api/voice/sessions`

Request:

```json
{
  "title": "Trip planning"
}
```

`title` is optional and may be `null`.

Response `201`:

```json
{
  "session": {
    "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "title": "Trip planning",
    "created_at": "2026-05-02T18:10:20.000Z",
    "updated_at": "2026-05-02T18:10:20.000Z",
    "last_message_preview": null,
    "message_count": 0,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "hermes_conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "archived_at": null
  }
}
```

### Get one session

`GET /api/voice/sessions/{session_id}`

Response `200`:

```json
{
  "session": {
    "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "title": "Trip planning",
    "created_at": "2026-05-02T18:10:20.000Z",
    "updated_at": "2026-05-02T18:14:03.000Z",
    "last_message_preview": "Let's compare those flight options.",
    "message_count": 6,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "hermes_conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "archived_at": null
  }
}
```

### Rename or archive

`PATCH /api/voice/sessions/{session_id}`

Request:

```json
{
  "title": "Flights and hotels",
  "archived": false
}
```

Response `200`:

```json
{
  "session": {
    "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "title": "Flights and hotels",
    "created_at": "2026-05-02T18:10:20.000Z",
    "updated_at": "2026-05-02T18:20:44.000Z",
    "last_message_preview": "Let's compare those flight options.",
    "message_count": 6,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "hermes_conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "archived_at": null
  }
}
```

### Soft delete

`DELETE /api/voice/sessions/{session_id}`

Response `200`:

```json
{
  "ok": true,
  "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "archived_at": "2026-05-02T18:25:00.000Z"
}
```

### Load messages

`GET /api/voice/sessions/{session_id}/messages`

Response `200`:

```json
{
  "messages": [
    {
      "id": "0af707fb-5878-4507-9b26-cdcaeae63e10",
      "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "turn_id": "1",
      "role": "user",
      "text": "Find me a nonstop flight to Boston next Friday.",
      "final": true,
      "created_at": "2026-05-02T18:12:02.000Z",
      "metadata": {
        "source": "stt"
      }
    },
    {
      "id": "c3978fd4-3ff4-449a-9632-dda7522b3759",
      "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "turn_id": "1",
      "role": "assistant",
      "text": "I can help compare nonstop options.",
      "final": true,
      "created_at": "2026-05-02T18:12:05.000Z",
      "metadata": {
        "source": "hermes"
      }
    }
  ]
}
```

## WebSocket API

Path remains:

```text
/ws/voice
```

### Create implicitly

Mobile may connect without `session_id`; the backend creates a persistent session.

Client:

```json
{
  "event": "client_hello",
  "client": "ios",
  "client_version": "0.0.1-dev",
  "accepted_downlink_formats": ["aac_adts", "wav_pcm16"]
}
```

Server:

```json
{
  "event": "session_started",
  "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1,
  "resumed": false,
  "created": true
}
```

### Resume

Client:

```json
{
  "event": "client_hello",
  "client": "ios",
  "client_version": "0.0.1-dev",
  "accepted_downlink_formats": ["aac_adts", "wav_pcm16"],
  "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42"
}
```

Server:

```json
{
  "event": "session_started",
  "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1,
  "resumed": true,
  "created": false
}
```

### Invalid session

Missing session id:

```json
{
  "event": "error",
  "error": {
    "code": "VOICE_SESSION_NOT_FOUND",
    "message": "Voice session not found",
    "status": 404
  }
}
```

Session owned by another principal:

```json
{
  "event": "error",
  "error": {
    "code": "VOICE_SESSION_FORBIDDEN",
    "message": "Voice session is not available for this account",
    "status": 403
  }
}
```

The server closes the socket after these errors.

### New session event

`new_session` now creates a new persistent voice session and a new Hermes conversation id. It cancels any active turn, clears buffered audio, leaves previous session/messages intact, and emits a fresh `session_started`.

Client:

```json
{
  "event": "new_session"
}
```

Server:

```json
{
  "event": "session_started",
  "session_id": "f4c42f5a-940c-49b4-a806-b7509bb1ec89",
  "conversation_id": "f4c42f5a-940c-49b4-a806-b7509bb1ec89",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1,
  "resumed": false,
  "created": true
}
```

## Message History Behavior

The server stores finalized text only:

- Final user transcript when the `transcript` frame is emitted.
- Final assistant text when an `assistant_text` frame with `final: true` is emitted.
- `turn_id`, role, text, final flag, timestamp, and small metadata.

The server does not store raw audio in V1. Stored messages are not replayed into Hermes. Hermes continuity is preserved by reusing the stable `conversation_id` in `stream_hermes_text()`, where the Hermes `/responses` payload still includes:

```json
{
  "conversation": "<stable-session-conversation-id>",
  "source": "voice",
  "instructions": "<VOICE_INSTRUCTIONS>"
}
```

## Mobile Checklist

- Use `/api/auth/login` and `/api/auth/verify`; retain the `hv_session` cookie.
- Load the sidebar from `GET /api/voice/sessions`.
- Create sidebar sessions with `POST /api/voice/sessions` when the user taps new chat.
- Connect `/ws/voice` with `client_hello.session_id` for selected or newly-created sessions.
- For first-run fallback, connecting without `session_id` is valid; save `session_started.session_id`.
- On reconnect or app relaunch, send the selected `session_id` in `client_hello`.
- Hydrate finalized transcript history from `GET /api/voice/sessions/{session_id}/messages`.
- Treat local message cache as a UI cache only, not Hermes memory.
- On `new_session`, expect a new sidebar session id from the next `session_started`.
- Handle `VOICE_SESSION_NOT_FOUND` and `VOICE_SESSION_FORBIDDEN` by returning to session selection or creating a new session.

## Tests Run

Targeted:

```bash
cd api
/home/limited_user/environments/hermes_voice/bin/pytest tests/test_voice_sessions.py tests/test_mobile_v06_protocol.py tests/test_websocket.py -q
```

Result: `25 passed`.

Full API suite:

```bash
cd api
/home/limited_user/environments/hermes_voice/bin/pytest -q
```

Result: `104 passed`.

## Known Limitations

- SQLite is the V1 persistence layer; no external database migration framework was introduced.
- Active in-flight turns are still canceled on disconnect.
- Archived sessions are omitted from list responses and are not resumable over WebSocket.
- Message history stores finalized text, not partial assistant deltas or audio.
- No mobile UI/client work was implemented in this backend phase.
