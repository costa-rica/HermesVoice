# 20260429 TODO — Hermes Voice Connection Status UX Simplification

Branch: `dev_02`
Implementer target: **Sonnet** (strict TDD)
Date (Pacific): 2026-04-29

## Goal

After mobile browser testing, the top connection badge shows "Connecting" most of the
time even when the app is fully usable. Root cause: internal `connState` transitions
(`connecting` on heartbeat/lifecycle reconnect) drive the badge directly, even while
`sessionReady` is true and the socket is open.

Replace the badge semantics with user-oriented states and add a manual check/reconnect
button so users have an explicit action instead of relying on fragile auto-detection.

## Design

### Badge States (`BadgeState`)
- `ready` → "Ready" (green) — `sessionReady` true, socket open; PTT usable
- `checking` → "Checking…" (yellow) — initial startup, reconnect in progress, or manual
  ping pending; transient, not a long-lived state
- `offline` → "Offline" (red/gray) — known closed/failed; PTT blocked

Internal `connState: ConnectionState` is unchanged (gates PTT via `sessionReady`).
Badge is driven by a separate `badgeState: BadgeState` field.

### Manual Check Button
- `#btn-check-conn`, `↻` icon, `title="Check connection"`, `aria-label="Check connection"`
- Placed next to the connection badge in the header
- If socket open: send ping with unique id → show `Checking…` → on matching pong →
  show `Ready` + toast "Connection checked"
- If pong timeout or socket closed: trigger reconnect → `Checking…` → on
  `session_started` → `Ready`

### Heartbeat Behavior
- Heartbeat pong timeout calls `triggerReconnect()` → badge shows `Checking…` (not
  `Connecting`)
- Heartbeat never sets badge to a long-lived `Connecting` state

## Scope

**In scope**
- `web/src/types.ts` — add `BadgeState`
- `web/src/ui.ts` — change `updateConnectionState` to accept `BadgeState`, add check
  button to `renderApp`, update badge label/CSS
- `web/src/app.ts` — `setBadgeState()`, `checkConnection()`, decouple badge from
  `setConnState`, manual check ping with ID tracking
- `web/src/style.css` — add `.badge.ready`, `.badge.checking`, `.badge.offline`,
  `.btn-check` styles
- `web/src/__tests__/connection-status-ux.test.ts` — new test file (TDD)

**Out of scope**
- Backend changes
- Native mobile / Swift iOS
- Auth / session management

## Acceptance Criteria

- [x] Badge shows "Ready" after `session_started` (not "Connected"/"Connecting")
- [x] Badge shows "Checking…" during initial connect and reconnect (never long-lived "Connecting")
- [x] Badge shows "Offline" immediately when socket closes
- [x] Manual check button (`#btn-check-conn`) renders with `title="Check connection"`
- [x] Clicking check button when socket open sends a ping and shows "Checking…"
- [x] Matching pong → badge "Ready" + toast "Connection checked"
- [x] Clicking check button when socket closed triggers reconnect
- [x] Heartbeat reconnect shows "Checking…" not "Connecting"
- [x] PTT gated by `sessionReady` (unchanged)
- [x] `cd web && npm test -- --run` → all tests green (18 passed 2026-04-29)
- [x] `cd web && npm run build` → no errors (2026-04-29)
- [x] `cd api && /home/limited_user/environments/hermes_voice/bin/pytest -q` → all green (64 passed 2026-04-29)

## Phases

### Phase 1 — Write failing tests

- [x] Create `web/src/__tests__/connection-status-ux.test.ts`
- [x] Test: badge is `ready` after `session_started`
- [x] Test: badge is `checking` during initial connect (before session)
- [x] Test: badge is `offline` after socket closes
- [x] Test: check button renders with accessible title
- [x] Test: check button sends ping + shows `checking` when socket open
- [x] Test: matching pong → `ready` + toast
- [x] Test: check button when socket closed → triggers reconnect
- [x] Test: heartbeat reconnect shows `checking` not `connecting`/`connected`
- [x] Test: PTT disabled before session, enabled after
- [x] Run `npm test`; confirm new tests FAIL for expected reasons

### Phase 2 — Implement changes

- [x] `types.ts`: add `BadgeState = 'ready' | 'checking' | 'offline'`
- [x] `ui.ts`: change `updateConnectionState(state: BadgeState)`, update badge text/CSS
- [x] `ui.ts`: add `#btn-check-conn` button to `renderApp` HTML template
- [x] `app.ts`: add `BadgeState` import, `badgeState` field, `setBadgeState()` method
- [x] `app.ts`: add `manualCheckPingId`, `manualCheckTimer` fields
- [x] `app.ts`: add `checkConnection()` method; wire to `#btn-check-conn`
- [x] `app.ts`: decouple `setConnState` from badge updates
- [x] `app.ts`: set badge explicitly in `start()`, `handleWsOpen()`, `session_started`,
  `handleWsClose()`, `triggerReconnect()`
- [x] `app.ts`: update `handlePong()` to detect manual-check pong by id
- [x] `style.css`: add `.badge.ready`, `.badge.checking`, `.badge.offline`, `.btn-check`
- [x] Run `npm test`; confirm all tests PASS (18/18 2026-04-29)

### Phase 3 — Final verification

- [x] `cd web && npm run build` → no errors (2026-04-29)
- [x] `cd api && /home/limited_user/environments/hermes_voice/bin/pytest -q` → all green (64 passed 2026-04-29)
- [x] Check off all acceptance criteria above
- [ ] Manual browser smoke test (Nick):
  1. Open tab — badge should show "Ready" (not "Connecting")
  2. Tap `↻` button — badge briefly shows "Checking…", then returns to "Ready" with toast
  3. Background tab for 30 s, restore — badge may show "Checking…" briefly, returns to "Ready"
  4. PTT works immediately after restore

## Commit Guidance

```
feat: connection status UX — Ready badge and manual check button

- refs 20260429_TODO_HERMES_VOICE_CONNECTION_STATUS_UX.md Phases 1-2
- replace Connected/Connecting/Disconnected badge with Ready/Checking/Offline
- add ↻ check button: ping when open, reconnect when closed
- decouple badge from internal connState to prevent Connecting while usable
- heartbeat reconnect shows Checking not Connecting
```
