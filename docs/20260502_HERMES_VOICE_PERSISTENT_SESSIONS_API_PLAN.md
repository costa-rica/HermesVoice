# HermesVoice persistent sessions API plan

## Purpose

We want the iOS app to keep conversations available after a temporary WebSocket drop, app backgrounding, app restart, or phone restart. The mobile app can store local UI history by itself, but true conversation resume requires API support because the backend currently creates one `conversation_id` per WebSocket connection and documented V1 reconnect behavior is a new session with no resume.

This document is for the server/API coding agent. Please verify the current backend architecture, implement the smallest stable API/protocol changes needed for persistent resumable sessions, push your changes, and create the return handoff document requested below.

## Current understanding

1. The iOS app connects to:
   - `wss://hermes-voice.dashanddata.com/ws/voice`
   - Local development may use `http://127.0.0.1:8700` / `ws://127.0.0.1:8700/ws/voice`.

2. The current WebSocket protocol includes:
   - `client_hello`
   - `session_started`
   - `conversation_id`
   - `start_utterance`
   - binary WAV audio upload
   - `end_of_utterance`
   - `transcript`
   - `assistant_text`
   - `audio_chunk` JSON prelude plus binary audio
   - `turn_id`
   - `cancel_turn`
   - `turn_end`

3. Current docs indicate:
   - Backend mints one `conversation_id` per WebSocket session.
   - `new_session` creates a fresh conversation id.
   - V1 reconnect behavior is a new session with no resume.

4. Mobile-side work planned after API changes:
   - Hamburger/sidebar session list.
   - Create new session.
   - Select previous session.
   - Persist local transcript/assistant history.
   - Reconnect WebSocket into the selected server session.

## Product behavior we want

1. A user can open the iOS app and see previous voice sessions.

2. A user can create a new session from the app.

3. A user can select an existing session and continue that conversation.

4. If the WebSocket disconnects temporarily, the app can reconnect to the same session.

5. If the app is closed and reopened, the app can restore the last selected session and continue.

6. The transcript shown on mobile should survive app restart. Ideally it comes from the API, but the first implementation may combine API session identity with mobile-local message persistence if that is simpler.

## Key architecture question for the API agent

Please determine and document whether Hermes conversation continuity is controlled by:

1. The backend's `conversation_id`.

2. A separate Hermes conversation id.

3. A message history payload sent to Hermes on each turn.

4. Some other backend/Hermes mechanism.

The implementation should preserve real Hermes context across reconnects, not only restore text in the mobile UI.

## Preferred API design

Please adjust as needed based on the existing backend patterns, but keep the mobile contract simple.

1. Add persistent voice session records.

   Suggested fields:
   - `id`: stable API session id, UUID string.
   - `title`: nullable or generated text label.
   - `created_at`: ISO timestamp.
   - `updated_at`: ISO timestamp.
   - `last_message_preview`: optional string.
   - `backend_conversation_id`: current existing `conversation_id` or equivalent.
   - `hermes_conversation_id`: if distinct from backend conversation id.
   - `archived_at` or `deleted_at`: optional.

2. Add HTTP endpoints for mobile session management.

   Suggested endpoints:
   - `GET /api/voice/sessions`
   - `POST /api/voice/sessions`
   - `GET /api/voice/sessions/{session_id}`
   - `PATCH /api/voice/sessions/{session_id}`
   - Optional: `DELETE /api/voice/sessions/{session_id}` or archive endpoint.

3. Add message history support if practical.

   Suggested endpoint:
   - `GET /api/voice/sessions/{session_id}/messages`

   Suggested message fields:
   - `id`
   - `session_id`
   - `turn_id`
   - `role`: `user` or `assistant`
   - `text`
   - `created_at`
   - Optional: `final`, `metadata`

4. Add WebSocket resume.

   Preferred option:
   - Let iOS include `session_id` in `client_hello`.

   Example:
   ```json
   {
     "event": "client_hello",
     "client": "ios",
     "client_version": "0.0.1-dev",
     "accepted_downlink_formats": ["wav_pcm16", "aac_adts"],
     "session_id": "<existing-session-id>"
   }
   ```

   Expected behavior:
   - If `session_id` is valid, attach this WebSocket to that persistent session.
   - If omitted, create a new persistent session.
   - If invalid or unauthorized, send an `error` frame with a stable code and close or reject according to existing backend style.

5. Extend `session_started`.

   Please include both the stable persistent session id and the active conversation id.

   Example:
   ```json
   {
     "event": "session_started",
     "session_id": "<persistent-session-id>",
     "conversation_id": "<active-conversation-id>",
     "downlink_format": "wav_pcm16",
     "downlink_sample_rate": 16000,
     "downlink_channels": 1,
     "resumed": true
   }
   ```

6. Persist transcript and assistant messages on the server if feasible.

   Minimum:
   - Store final user transcript when STT completes.
   - Store final assistant text when the assistant response completes or as text deltas arrive.

   Nice to have:
   - Store turn lifecycle timestamps.
   - Store errors or skipped-turn metadata.

## Authentication and ownership

1. Sessions must be scoped to the authenticated user/session.

2. A mobile user must not be able to resume another user's session id.

3. Keep existing browser behavior compatible.

4. If bearer-token mobile auth and cookie browser auth both exist, document which one was tested.

## Backend implementation guidance

1. Prefer additive protocol changes.

2. Do not break existing web client behavior.

3. Keep `conversation_id` in existing frames for compatibility.

4. Add `session_id` where useful, especially `session_started`.

5. Ensure `cancel_turn` still works after reconnect.

6. On WebSocket disconnect:
   - Cancel active turn if current backend behavior requires it.
   - Do not delete the persistent session.
   - Keep stored message history.

7. On reconnect:
   - Resume the persistent session.
   - Preserve Hermes context if possible.
   - Return enough metadata for mobile to know it resumed the intended session.

## Tests requested

Please add or update backend tests for:

1. Creating a voice session.

2. Listing sessions for the authenticated user.

3. Rejecting access to another user's session.

4. WebSocket connect without `session_id` creates a persistent session and returns it in `session_started`.

5. WebSocket connect with a valid `session_id` resumes that session and returns `resumed: true`.

6. WebSocket reconnect does not lose stored transcript or assistant messages.

7. Existing web client without `client_hello.session_id` still works.

8. `new_session` behavior is still clear:
   - Either it creates a new persistent session.
   - Or it only rotates the active backend conversation inside the same persistent session.
   - Please choose and document the behavior.

## What the mobile agent needs after API work

Please make sure the handoff gives the mobile agent:

1. Exact HTTP endpoints and JSON response examples.

2. Exact WebSocket `client_hello` shape for creating and resuming sessions.

3. Exact `session_started` response shape.

4. Whether the app should call HTTP `POST /api/voice/sessions` before opening the socket, or whether opening the socket without `session_id` creates the session.

5. Whether message history should be loaded from the API or stored only on-device for now.

6. The rules for `new_session`.

7. Any migration or database setup commands.

8. Test commands run and results.

9. Branch name, commit hash, and PR link if available.

## Return handoff document required

Please create a new docs file before handing back:

`docs/20260502_HERMES_VOICE_PERSISTENT_SESSIONS_API_HANDOFF.md`

That file should include:

1. Summary of implemented backend behavior.

2. Files changed.

3. Database/schema changes.

4. HTTP API contract with examples.

5. WebSocket API contract with examples.

6. Auth/session ownership notes.

7. Test commands and results.

8. Manual verification steps.

9. Mobile implementation checklist.

10. Known limitations or unresolved questions.

## Acceptance criteria for server/API phase

1. Backend tests pass.

2. Existing web voice flow still works.

3. New iOS-compatible session create/resume flow is documented and tested.

4. A WebSocket reconnect can resume the same persistent session id.

5. The handoff document exists and is detailed enough for the mobile agent to implement without guessing.

