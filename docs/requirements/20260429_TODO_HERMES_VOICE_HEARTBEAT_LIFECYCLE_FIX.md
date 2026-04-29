# 20260429 TODO — Hermes Voice Heartbeat Lifecycle Fix

Branch: `dev_02`
Implementer target: **Sonnet** (strict TDD)
Date (Pacific): 2026-04-29

## Goal

After the stale-connection recovery feature (Phase 4 of usability fixes), the connection
label is "Connecting" most of the time instead of "Connected". Root cause: the heartbeat
pong timeout fires late when browser throttles/freezes timers while a tab is hidden,
triggering a false `triggerReconnect()` on restore.

## Diagnosis

- Heartbeat pong timeout fires after tab restore because browser throttled timers while
  hidden → false `triggerReconnect()` → label shows "Connecting".
- `visibilitychange`, `pageshow`, and `focus` can all fire together and trigger duplicate
  or aggressive reconnect checks.
- Server sends `session_started` immediately; backend is not the issue.

## Fix Summary

1. Pause/stop heartbeat (clear interval + discard pong timer) when document goes hidden.
2. On restore (visible/pageshow), discard stale pong timer before making recovery decisions.
3. Debounce lifecycle recovery: rapid `visibilitychange` + `pageshow` coalesce to one
   recovery attempt (300 ms window).
4. Remove `window.focus` recovery; prefer `visibilitychange` / `pageshow`.
5. Guard in pong timeout callback: skip reconnect if `document.visibilityState === 'hidden'`
   (belt-and-suspenders for the hide→pong-fires race).
6. Resume heartbeat after tab restore if socket is open.

## Scope

**In scope**
- `web/src/app.ts` — heartbeat pause/resume, lifecycle debounce
- `web/src/__tests__/heartbeat-lifecycle.test.ts` (new, with vitest)
- `web/package.json` — add vitest + jsdom devDependencies + test script
- `web/vitest.config.ts` — new vitest config

**Out of scope**
- Backend changes
- Mobile / Flutter
- Auth / session management

## Acceptance Criteria

- [x] Hiding the tab stops the heartbeat interval and clears any pending pong timer.
- [x] Restoring the tab when socket is open and `sessionReady` does NOT trigger reconnect.
- [x] Restoring the tab when socket is closed DOES trigger reconnect.
- [x] Rapid lifecycle events (`visibilitychange` + `pageshow`) are debounced to one recovery.
- [x] Heartbeat resumes after tab restore when socket is open.
- [x] Pong timeout with `visibilityState === 'hidden'` does not trigger reconnect.
- [x] `cd api && /home/limited_user/environments/hermes_voice/bin/pytest -q` → all green (64 passed 2026-04-29).
- [x] `cd web && npm run build` → no errors (2026-04-29).

## Phases

### Phase 1 — Add vitest test infrastructure

- [x] Add `vitest` + `jsdom` to `web/package.json` devDependencies.
- [x] Add `test` script to `web/package.json`.
- [x] Create `web/vitest.config.ts` with jsdom environment.
- [x] Confirm `npm test` runs (even with zero tests) without error.

### Phase 2 — Write failing tests

- [x] Create `web/src/__tests__/heartbeat-lifecycle.test.ts`.
- [x] Test: hidden visibility stops heartbeat and clears pong timer; no false reconnect.
- [x] Test: visible/pageshow does NOT reconnect when socket open + sessionReady.
- [x] Test: visible/pageshow triggers reconnect when socket closed.
- [x] Test: rapid lifecycle events are debounced to a single recovery.
- [x] Test: heartbeat resumes after tab restore.
- [x] Test: pong timeout guard — hidden page prevents reconnect even if timer fires.
- [x] Run `npm test`; confirm 3 of 7 tests FAIL for the expected reasons.

### Phase 3 — Implement fixes in app.ts

- [x] Add `lifecycleRecoveryTimer` field.
- [x] `handleVisibilityChange`: call `stopHeartbeat()` on hidden; call
  `scheduleLifecycleRecovery()` on visible.
- [x] `handlePageShow`: call `scheduleLifecycleRecovery()`.
- [x] Remove `window.focus` event listener and `handleWindowFocus` method.
- [x] Add `scheduleLifecycleRecovery()`: 300 ms debounce that discards stale pong timer,
  calls `checkAndRecoverConnection()`, resumes heartbeat if socket open.
- [x] In `sendHeartbeat` pong timeout callback: return early if
  `document.visibilityState === 'hidden'`.
- [x] Run `npm test`; confirm all 7 tests PASS.

### Phase 4 — Final verification

- [x] `cd api && /home/limited_user/environments/hermes_voice/bin/pytest -q` → all green (64 passed 2026-04-29).
- [x] `cd web && npm run build` → no errors (2026-04-29).
- [x] Check off all phase boxes above.
- [ ] Manual browser smoke test (Nick):
  1. Open tab, confirm label stays "Connected" (not "Connecting").
  2. Background tab for 30s, restore — label should briefly show "Connecting" only if
     truly reconnecting, then return to "Connected".
  3. PTT works immediately after restore without extra "reconnecting" toast.

## Commit Guidance

```
fix: prevent false reconnect on tab restore

- refs 20260429_TODO_HERMES_VOICE_HEARTBEAT_LIFECYCLE_FIX.md Phase 3
- stop heartbeat on hide; discard stale pong timer before recovery checks
- debounce visibilitychange/pageshow to one recovery attempt
- remove noisy focus handler; guard pong timeout against hidden page
```
