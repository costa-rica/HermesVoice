# HermesVoice persistent sessions mobile handoff draft

Date: 2026-05-02
Branch reviewed: `dev_05_persistence`
Status: superseded. The implemented backend/API contract is now documented in
`docs/20260502_HERMES_VOICE_PERSISTENT_SESSIONS_API_HANDOFF.md`.

## Review decision

The API/backend persistence feature can be implemented safely and additively.

The existing backend already has the key property needed for real Hermes continuity: `api/app/routes/voice.py` creates a `conversation_id` for the WebSocket and passes it into `api/app/services/pipeline.py`, which calls `stream_hermes_text()` in `api/app/services/hermes.py`. `stream_hermes_text()` sends that value to the Hermes gateway as the `/responses` JSON field:

```json
{
  "conversation": "<conversation_id>",
  "source": "voice",
  "instructions": "<VOICE_INSTRUCTIONS>"
}
```

Persistent sessions should therefore preserve and reuse the Hermes conversation value across reconnects. Mobile should not reimplement Hermes memory by replaying local messages.

## Architecture decision

Use one stable API voice session id as the persistent Hermes conversation id in V1.

Recommended storage fields:

```json
{
  "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "hermes_conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42"
}
```

The WebSocket `conversation_id` remains the active Hermes conversation id for backward compatibility. In V1 it should equal `hermes_conversation_id`, which should normally equal `session_id`.

Keep a separate `hermes_conversation_id` column internally anyway. That leaves room for a future migration if Hermes later returns or requires an opaque conversation id distinct from the public voice session id.

## Auth and ownership

Sessions must be scoped to an authenticated owner. A caller must not be able to list, fetch, resume, patch, delete, or read messages for another owner's session.

Current auth state:

- Browser and mobile auth use the signed `hv_session` cookie.
- WebSocket also accepts a bearer API key via `Authorization: Bearer ***`.
- The current cookie payload proves only `authenticated`; it does not expose a stable user subject.
- The bearer key is shared configuration, not an end-user identity.

Required API implementation prerequisite:

- Add an auth principal helper used by HTTP and WebSocket routes.
- For new cookie sessions, sign a payload containing at least the normalized email, for example `{"sub":"allowed@example.com","auth_type":"cookie"}`.
- Keep existing browser compatibility by accepting old boolean/string cookie payloads for basic web access, but do not allow legacy ownerless cookies to access another user's persistent sessions.
- Recommended behavior for a legacy cookie on session APIs: return `401 AUTH_FAILED` or require re-login so the server can mint an owner-bearing cookie.
- Treat bearer/API-key auth as a development or service fallback. If enabled for session APIs, scope it to a synthetic owner such as `api_key:<fingerprint>`, not to a global shared mobile user.

Mobile should prefer the normal cookie auth flow and should not ship with an embedded bearer key.

## HTTP API contract

All endpoints require auth. Responses use JSON. Error frames should follow the existing error shape:

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
      "created_at": "2026-05-02T18:10:20Z",
      "updated_at": "2026-05-02T18:14:03Z",
      "last_message_preview": "Let's compare those flight options.",
      "message_count": 6,
      "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "archived_at": null
    }
  ]
}
```

Default ordering: newest `updated_at` first. Archived sessions should be omitted by default.

### Create session

`POST /api/voice/sessions`

Request:

```json
{
  "title": "Trip planning"
}
```

`title` is optional and nullable. The server may generate a title later from the first user message.

Response `201`:

```json
{
  "session": {
    "id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "title": "Trip planning",
    "created_at": "2026-05-02T18:10:20Z",
    "updated_at": "2026-05-02T18:10:20Z",
    "last_message_preview": null,
    "message_count": 0,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
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
    "created_at": "2026-05-02T18:10:20Z",
    "updated_at": "2026-05-02T18:14:03Z",
    "last_message_preview": "Let's compare those flight options.",
    "message_count": 6,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "archived_at": null
  }
}
```

### Rename or archive a session

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
    "created_at": "2026-05-02T18:10:20Z",
    "updated_at": "2026-05-02T18:20:44Z",
    "last_message_preview": "Let's compare those flight options.",
    "message_count": 6,
    "conversation_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
    "archived_at": null
  }
}
```

### Archive/delete a session

Recommended V1 behavior is soft-delete/archive, not hard delete.

`DELETE /api/voice/sessions/{session_id}`

Response `200`:

```json
{
  "ok": true,
  "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
  "archived_at": "2026-05-02T18:25:00Z"
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
      "created_at": "2026-05-02T18:12:02Z",
      "metadata": {}
    },
    {
      "id": "c3978fd4-3ff4-449a-9632-dda7522b3759",
      "session_id": "8dfd75c9-7c34-4f1e-928f-7b0222f9bb42",
      "turn_id": "1",
      "role": "assistant",
      "text": "I can help compare nonstop options. What airport are you leaving from?",
      "final": true,
      "created_at": "2026-05-02T18:12:05Z",
      "metadata": {}
    }
  ]
}
```

Recommended V1: server message history is the source of truth for finalized transcript and assistant text. Mobile may keep an on-device cache for instant UI restore and offline display, but should hydrate from this endpoint after login/app launch and after selecting a session.

## WebSocket contract

Path remains:

`/ws/voice`

Existing browser behavior must remain compatible:

- Browser may omit `client_hello`.
- Browser may omit `client_hello.session_id`.
- `session_started.conversation_id` must remain present.
- Existing downlink fields must remain present.

### Create implicitly over WebSocket

Mobile may open the socket without a `session_id`. The server creates a persistent voice session and returns it in `session_started`.

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

### Resume over WebSocket

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

### Invalid or unauthorized session id

Server should send a typed error and close the socket.

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

For valid-but-not-owned sessions:

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

## Should mobile POST before opening the socket?

Recommended mobile behavior:

- For the sidebar "new chat" button: call `POST /api/voice/sessions` first, store the returned `session.id`, then connect the WebSocket with `client_hello.session_id`.
- For first-run/simple push-to-talk startup: it is acceptable to connect without `session_id`; the backend creates a session implicitly and returns `session_id` in `session_started`.
- For reconnect/app relaunch/session selection: always send the selected `session_id` in `client_hello`.

The explicit POST path is easier for UI because the app can add the session to the list before audio starts. The implicit WebSocket path preserves compatibility and gives a low-friction fallback.

## `new_session` behavior

Recommended V1 behavior: `new_session` creates a new persistent voice session.

Rationale: mobile users expect "new session" to create a new sidebar item and a new Hermes conversation. Rotating only the Hermes conversation inside the same persistent session would make session history ambiguous.

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

The server should cancel any active turn, clear buffered audio, leave the previous persistent session and messages intact, and start the socket on the new session.

## Message persistence rules

Recommended V1 persistence:

- Store the final user transcript when STT completes and the `transcript` frame is sent.
- Store the final assistant text when the final `assistant_text` frame is sent.
- Store `turn_id`, role, text, final flag, timestamps, and minimal metadata.
- Do not store raw audio in V1.
- Do not replay stored messages back into Hermes on every turn. Hermes continuity comes from the stable `conversation` value sent to `/responses`.

If a turn is canceled or disconnects mid-turn:

- Current backend behavior cancels the active turn on WebSocket disconnect.
- Persist only finalized messages that were already emitted.
- Do not delete the persistent session.
- On reconnect, mobile should reload messages and continue with a new turn.

## Backend implementation checklist

- Add persistent storage for voice sessions and voice messages. The repo currently has no database layer or migration pattern, so the API implementation must introduce one deliberately.
- Add settings for the persistence database path, for example `HERMES_VOICE_DB_PATH`.
- Add startup initialization for the schema.
- Add an auth principal helper shared by HTTP and WebSocket routes.
- Update cookie creation to include a stable subject for new sessions while preserving existing browser compatibility.
- Add `GET/POST/PATCH/DELETE /api/voice/sessions` routes.
- Add `GET /api/voice/sessions/{session_id}/messages`.
- Extend `client_hello` parsing to read optional `session_id`.
- On WebSocket connect without `session_id`, create a persistent session.
- On WebSocket connect with `session_id`, verify ownership and resume that session.
- Pass the session's `hermes_conversation_id` as `conversation_id` into `run_voice_turn()`.
- Preserve `source="voice"` and `VOICE_INSTRUCTIONS` in the Hermes call.
- Extend `session_started` with `session_id`, `resumed`, and `created`, while keeping existing fields.
- Make `new_session` create a new persistent session and emit another extended `session_started`.
- Add message persistence around final `transcript` and final `assistant_text` frames.
- Keep existing V06 downlink negotiation and turn-id behavior unchanged.
- If browser code later uses `PATCH` or `DELETE`, update FastAPI CORS `allow_methods`; native mobile is not blocked by browser CORS.

## Test expectations

Backend tests should cover:

- `POST /api/voice/sessions` creates a session for an authenticated owner.
- `GET /api/voice/sessions` lists only the caller's sessions.
- `GET /api/voice/sessions/{session_id}` rejects another owner's session.
- `PATCH /api/voice/sessions/{session_id}` updates title/archive fields for the owner.
- `DELETE /api/voice/sessions/{session_id}` archives rather than hard-deletes.
- `GET /api/voice/sessions/{session_id}/messages` returns only the owner's messages.
- WebSocket without `client_hello.session_id` creates a persistent session and returns `session_id`.
- WebSocket with a valid owned `session_id` resumes and returns `resumed: true`.
- WebSocket with another owner's `session_id` returns `VOICE_SESSION_FORBIDDEN`.
- WebSocket with a missing `session_id` returns `VOICE_SESSION_NOT_FOUND`.
- Existing browser path without `client_hello` still receives `session_started.conversation_id`.
- Existing browser/mobile tests expecting downlink fields still pass.
- `new_session` emits a different `session_id` and `conversation_id`.
- A resumed session passes the same stable `conversation_id` into `stream_hermes_text()`.
- Hermes payload still includes `source="voice"` and `instructions=VOICE_INSTRUCTIONS`.
- Stored transcript and assistant messages survive WebSocket reconnect.

Recommended narrow command after implementation:

```bash
cd api
python3 -m pytest tests/test_auth.py tests/test_mobile_auth.py tests/test_mobile_v06_protocol.py tests/test_websocket.py -q
```

Recommended full command:

```bash
cd api
python3 -m pytest -q
```

## Known limitations before implementation

- These endpoints are not implemented yet.
- The current repo has no database abstraction or migration framework.
- Existing signed cookies do not contain a user subject; user-scoped session APIs need an auth-principal change first.
- The bearer API key is not a mobile end-user identity and should not be embedded in the iOS app.
- Server message history should be considered finalized text history, not Hermes memory.
- Active in-flight turns are still canceled on disconnect in V1.
- No mobile code should be changed until the backend contract is implemented and tested.
