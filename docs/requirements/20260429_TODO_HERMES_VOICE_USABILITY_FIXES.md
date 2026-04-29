# 20260429 TODO — Hermes Voice Usability Fixes

Branch: `dev_02`
Implementer target: **Sonnet** (strict TDD; no Opus required)
Date (Pacific): 2026-04-29

## Goal

Four improvements identified during Nick's live test session:

1. **Interrupt / cancel-thinking** — users need a way to cancel a running turn
   (Hermes thinking / speaking) without waiting for it to finish.
2. **Stale connection recovery** — after the browser is backgrounded/locked and
   restored, the WebSocket may be half-open; PTT must not silently do nothing.
3. **audio_too_short UI feedback** — when the backend skips a turn because the
   audio is too short, the UI looks dead; the user needs visible feedback.
4. **Heartbeat / liveness check** (optional, best-effort) — detect half-open
   sockets after browser suspension without waiting for the next PTT attempt.

## Background

Live test showed:
- Long Hermes turns work after Phase 6 changes but there is no way to interrupt.
- After locking screen and returning, the WebSocket reconnect fires but
  `session_started` may not arrive before the user presses PTT, causing the
  press to be silently ignored (the existing guard `turnState !== 'idle' || !isOpen`
  returns early with no feedback).
- Tiny accidental taps produce a `voice_turn_skipped` frame from the backend
  but the frontend does not handle it; the UI shows the last state indefinitely.
- Logs show idle-timeout closes followed by reconnects, indicating sockets
  can go stale during extended idle periods.

## Scope

**In scope**
- Backend: handle `cancel_turn` WebSocket event → cancel active task, emit
  `active_state=idle` + `turn_end`.
- Backend: handle `ping` → respond `pong`.
- Frontend: cancel button visible only while thinking/thinking_progress/speaking.
- Frontend: handle `voice_turn_skipped` → show brief "audio too short" status.
- Frontend: `visibilitychange` / `pageshow` / `focus` handlers to detect stale
  connection and trigger reconnect; `sessionReady` gate before PTT.
- Frontend: periodic ping with reconnect-on-timeout.

**Out of scope**
- Mobile / Flutter code.
- Reworking auth or session management.
- Changes to STT / TTS / Hermes pipeline logic.

## Acceptance Criteria

- [x] Sending `cancel_turn` over the WebSocket cancels the active turn and
  returns the UI to idle.
- [x] A cancel button appears while turnState is thinking / thinking_progress /
  speaking, and is hidden otherwise.
- [x] After backgrounding and restoring the browser tab, the first PTT press
  either works or shows a visible status ("reconnecting…") instead of silently
  failing.
- [x] A deliberate tiny tap produces a visible "audio too short" or "didn't
  catch that" indicator rather than leaving the UI frozen.
- [x] Sending `ping` over the WebSocket results in a `pong` response.
- [x] All new backend behavior covered by failing-first tests under `api/tests/`.
- [x] `cd api && python -m pytest -q` passes (64 passed 2026-04-29).
- [x] `cd web && npm run build` passes (2026-04-29).

## Files Likely Touched

Backend
- `api/app/routes/voice.py` — `cancel_turn` and `ping` event handlers

Frontend
- `web/src/types.ts` — `WsVoiceTurnSkipped`, `WsCancelTurn`, `WsPing/Pong` types
- `web/src/ui.ts` — cancel button in HTML, show/hide logic
- `web/src/ws.ts` — `sendPing`, expose `isConnecting` state
- `web/src/app.ts` — cancel handler, `voice_turn_skipped` handler,
  `visibilitychange`/`pageshow`/`focus` handlers, sessionReady gate, heartbeat

Tests
- `api/tests/test_cancel_turn.py` (new)
- `api/tests/test_ping_pong.py` (new)
- Web: no test framework — `npm run build` only; manual browser verification needed

Docs
- This TODO file checked off per phase

## TDD Discipline

For every phase:
1. Write the new test(s) first. Run them; confirm they fail for the right reason.
2. Implement the smallest change that turns the tests green.
3. Run the full `api` suite. Fix any regressions.
4. Commit per the per-phase commit guidance below.

## Phases

### Phase 1 — cancel_turn backend

- [x] Write `api/tests/test_cancel_turn.py`:
  - `cancel_turn` with no active task → receives `active_state=idle` + `turn_end`
  - `cancel_turn` is not an error frame; connection stays open
- [x] In `voice.py`, handle `event == "cancel_turn"`:
  - Call `cancel_active_turn()`
  - Reset utterance state
  - Emit `active_state=idle`, `turn_end`
- [x] Run `pytest tests/test_cancel_turn.py -v`; confirm green.
- [x] Run full suite; fix regressions.

### Phase 2 — ping/pong backend

- [x] Write `api/tests/test_ping_pong.py`:
  - Sending `ping` frame returns `pong` frame with same `id` if present
  - Connection stays open after pong
- [x] In `voice.py`, handle `event == "ping"`:
  - Respond `{"event": "pong", "id": frame.get("id")}` (omit id if not present)
- [x] Run `pytest tests/test_ping_pong.py -v`; confirm green.
- [x] Run full suite; fix regressions.

### Phase 3 — audio_too_short UI feedback (frontend)

- [x] Add `WsVoiceTurnSkipped` type to `types.ts` and add to `WsJsonFrame` union.
- [x] In `app.ts`, handle `voice_turn_skipped` event:
  - Show brief visible status (e.g. "Audio too short — tap and hold longer")
  - Set turn state to `idle`
- [x] `npm run build` passes.

### Phase 4 — cancel button and visibilitychange recovery (frontend)

- [x] Add cancel button to `renderApp()` HTML in `ui.ts`.
- [x] `updateTurnState()` shows cancel button for thinking/thinking_progress/speaking,
  hides otherwise.
- [x] In `app.ts`:
  - Wire cancel button → send `cancel_turn` event
  - Add `sessionReady` flag (true after `session_started`, false after close/error)
  - PTT guard: if not `sessionReady` or not idle, show visible status rather than silently no-op
  - Add `visibilitychange`/`pageshow`/`focus` handlers: if hidden→visible and
    socket not open, trigger reconnect; reset `sessionReady` and turn state
  - Add heartbeat: every `HEARTBEAT_INTERVAL_MS` send ping; if no pong within
    `HEARTBEAT_TIMEOUT_MS` close/reconnect
- [x] `npm run build` passes.

### Phase 5 — Final verification and commit cleanup

- [x] `cd api && /home/limited_user/environments/hermes_voice/bin/pytest -q` → all green (64 passed 2026-04-29).
- [x] `cd web && npm run build` → no errors (2026-04-29).
- [x] Check off all phase boxes above.
- [ ] Manual browser smoke test (Nick):
  1. Press cancel during a long Hermes turn → turn stops, UI returns to idle.
  2. Background and restore tab → PTT shows "reconnecting" or works correctly.
  3. Tiny accidental tap → "audio too short" visible message.
  4. Monitor console for heartbeat ping/pong in dev tools.

## Commit Guidance

Per `docs/CommitMessagesGuidance.md`. One commit per phase.

```
feat: add cancel_turn websocket event

- refs 20260429_TODO_HERMES_VOICE_USABILITY_FIXES.md Phase 1
- cancel_turn event cancels active pipeline task and resets to idle
- emits active_state=idle + turn_end so UI can recover
```

```
feat: add ping/pong websocket heartbeat handler

- refs 20260429_TODO_HERMES_VOICE_USABILITY_FIXES.md Phase 2
```

```
feat: audio_too_short frontend feedback

- refs 20260429_TODO_HERMES_VOICE_USABILITY_FIXES.md Phase 3
```

```
feat: cancel button and stale-connection recovery

- refs 20260429_TODO_HERMES_VOICE_USABILITY_FIXES.md Phase 4
- cancel button visible during thinking/speaking turns
- visibilitychange/pageshow/focus reconnect on stale socket
- sessionReady gate prevents silent PTT no-ops
- client-side heartbeat detects half-open sockets
```
