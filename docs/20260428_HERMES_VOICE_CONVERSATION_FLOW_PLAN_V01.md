# HermesVoice Conversation Flow Plan V01

Date: 2026-04-28
Branch: `dev_02`
Scope: web client (`web/`) + FastAPI backend (`api/`). Mobile app is **not** in scope.

This is a planning document only. No code changes are made by this plan; an
implementation TODO file under `docs/requirements/` will be authored after
this plan is reviewed (per `docs/TODO_LIST_GUIDANCE.md`).

---

## 1. Goals (from user feedback)

1. **Fluid conversation flow** — multi-turn dialog should continue cleanly
   without manual reload or re-handshake.
2. **Active-state indicator** — a clear visual signal when HermesVoice is
   listening, thinking, speaking, or idle.
3. **Command-approval UI** — when Hermes asks permission to run a tool /
   command, the user must be able to approve or deny it from the web UI.
4. **Multi-turn reliability** — verify and fix the bug where after the first
   exchange, subsequent assistant responses fail to come through.
5. **Chat-style transcript** — render user-side and Hermes-side text in
   distinct visual bubbles, retained as a conversation log.

## 2. Framework choice: stay on Vite

**Decision: keep Vite + vanilla TypeScript. Do not introduce Next.js.**

Reasons:

- The web client is a single-screen voice validation tool. There is no SSR,
  no routing, no SEO surface, no auth-gated multi-page app — none of the
  things Next.js exists to solve.
- All the requested features (chat bubbles, active-state badge, an approval
  modal, multi-turn flow) are pure client-side DOM + WebSocket work. They
  fit cleanly inside the existing `app.ts` / `ui.ts` / `ws.ts` split.
- Switching to Next.js would force a new toolchain, server runtime,
  hydration model, and build pipeline for zero functional gain — and would
  conflict with the FastAPI-served static-file deploy model already in use.
- Repo guidance (`docs/` build mandate) explicitly favors keeping the web
  validator small.

Vite remains sufficient. Continue using vanilla TS modules.

## 3. Feasibility constraints

- Hermes upstream emits SSE events; only `response.output_text.delta` is
  currently consumed (`api/app/services/hermes.py:21`,
  `api/app/services/hermes.py:90`). The exact event-type strings for tool /
  command approval requests are **not yet confirmed in this repo** and must
  be probed before the approval feature can be finalized — see Open
  Questions (§10).
- The pipeline currently chunks Hermes deltas only for TTS; the assistant
  text is **never forwarded as a JSON frame to the web client**
  (`api/app/services/pipeline.py:81-101`). That is the most likely root
  cause of "no chat bubble appears" and is also blocking goal #5.
- WebSocket protocol is JSON frames + binary audio; we will extend the
  JSON frame vocabulary, not change framing.
- No persistence layer is in scope — chat history lives in browser memory
  only for this validator.

## 4. Target architecture

### Backend (`api/app/`)

- `services/hermes.py` — broaden to surface multiple event types from the
  Hermes SSE stream:
  - `response.output_text.delta` (existing, speakable)
  - assistant final text (for transcript completeness)
  - tool/permission request events (exact names TBD — see §10)
  - tool/permission approval ack / completion events
  Refactor `stream_hermes_text` into a more general
  `stream_hermes_events` generator that yields a tagged union
  (`{"kind": "text_delta" | "assistant_text" | "approval_request" | ...}`),
  with a thin `stream_hermes_text` wrapper kept for the existing TTS path
  if convenient.
- `services/pipeline.py` — consume the broader event stream and emit the
  new WebSocket frames (see §5). Keep TTS chunking logic intact for
  `text_delta` events.
- `routes/voice.py` — add handling for an inbound `approval_response`
  frame from the client and forward the decision back to Hermes
  (mechanism depends on §10 resolution: either a follow-up POST to
  Hermes, or sent on the same SSE-bound channel via a separate request).

### Web (`web/src/`)

- `types.ts` — add new frame interfaces and a `ChatMessage` type.
- `ws.ts` — no structural change, still framing-agnostic.
- `ui.ts` — replace the single `#transcript` div with a scrollable
  `#chat-log` rendering message bubbles. Add a more prominent active-state
  indicator. Add an approval-prompt panel.
- `app.ts` — add chat log state, append user transcript and assistant text
  as discrete messages, handle approval frames.
- `style.css` (or co-located styles) — bubble styles for `user` vs
  `assistant`, active-state colors, modal styles.

## 5. WebSocket protocol changes

Existing server→client frames stay (`session_started`, `transcript`,
`turn_started`, `turn_completed`, `turn_end`, `error`, plus binary audio).

### New server→client frames

| event                 | shape                                                                                  | purpose                                     |
| --------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------- |
| `assistant_text`      | `{ event, text, final: bool }`                                                         | Render Hermes message into chat log.        |
| `assistant_text_delta`| `{ event, delta }` (optional / phase 4)                                                | Incremental chat-bubble streaming.          |
| `approval_request`    | `{ event, request_id, command, description, args? }`                                   | Trigger approval UI.                        |
| `approval_resolved`   | `{ event, request_id, decision: "approved"\|"denied", outcome?: string }`              | Tell UI a request is closed (e.g. timeout).|
| `active_state`        | `{ event, state: "idle"\|"listening"\|"thinking"\|"speaking"\|"awaiting_approval" }`   | Single source of truth for indicator.       |

### New client→server frames

| event                 | shape                                              | purpose                          |
| --------------------- | -------------------------------------------------- | -------------------------------- |
| `approval_response`   | `{ event, request_id, decision: "approved"\|"denied" }` | User answer to an approval. |

Notes:

- `active_state` is derivable from the existing `turn_started` /
  `turn_completed` etc., but a dedicated frame lets the backend signal the
  new `awaiting_approval` state and keeps the UI logic simpler.
- All new fields are additive; old clients keep working until rebuilt.

## 6. UI changes (web)

### 6.1 Chat log

- Replace `#transcript` (`web/src/ui.ts:42`) with `#chat-log`, a flex
  column of bubble elements.
- Bubble component (function `renderMessage(msg: ChatMessage)`) returns
  HTML for `.bubble.bubble-user` (right-aligned) or
  `.bubble.bubble-assistant` (left-aligned).
- `app.ts` keeps `messages: ChatMessage[]` and re-renders / appends on
  every `transcript` (user side) and `assistant_text` (assistant side).
- Auto-scroll to bottom on append.

### 6.2 Active-state indicator

- Replace the small `#turn-state` text in `web/src/ui.ts:43` with a
  pill/badge in the header, color-coded:
  - idle — neutral
  - listening (recording) — green pulse
  - thinking (transcribing/Hermes) — amber
  - speaking (TTS playing) — blue
  - awaiting_approval — red highlight
- Driven by the new `active_state` frame, with local fallbacks (e.g. set
  to `listening` immediately on PTT press for responsiveness).

### 6.3 Approval prompt

- A modal/panel `#approval-panel`, hidden by default.
- On `approval_request`: show the panel with `description`, `command`,
  optional `args`; render Approve / Deny buttons.
- Both buttons send `approval_response` and locally hide the panel
  (server is authoritative — `approval_resolved` will also hide it).
- If multiple approvals stack, queue them; show one at a time.

## 7. Backend changes

### 7.1 `api/app/services/hermes.py`

- Refactor to `stream_hermes_events(text, conversation_id) -> AsyncIterator[dict]`
  yielding tagged events.
- Keep `stream_hermes_text` as a thin filter for back-compat in tests.
- Capture and surface:
  - text deltas
  - the final assistant message text (concat of deltas if upstream does
    not emit a single final event)
  - approval / tool-call events (gated on §10 outcome; if unknown, log
    raw `etype` strings during a discovery phase to identify them).

### 7.2 `api/app/services/pipeline.py`

- Switch from `_chunk_hermes_text` consuming `stream_hermes_text` to
  consuming the new event generator. For `text_delta` items, feed the
  existing TTS chunker. For `assistant_text` (or accumulated final),
  emit `{"event": "assistant_text", "text": ..., "final": true}`.
- Emit `{"event": "active_state", "state": "thinking"}` when STT
  finishes, `"speaking"` on first audio chunk, `"awaiting_approval"`
  when an approval event arrives, and `"idle"` on turn end.
- On approval request: emit `approval_request` to client and **suspend**
  the turn pipeline awaiting an `approval_response`. A `Future` keyed by
  `request_id` (held in `routes/voice.py` per-connection) resolves it.
- On timeout (configurable, e.g. `APPROVAL_TIMEOUT=60s`): emit
  `approval_resolved` with `decision: "denied"` and continue/abort.

### 7.3 `api/app/routes/voice.py`

- Add `approval_response` to the inbound JSON dispatch in the
  `websocket.receive` loop (`api/app/routes/voice.py:138-200`).
- Maintain a per-connection `pending_approvals: dict[str, asyncio.Future]`.
- On inbound `approval_response`, resolve the matching future; ignore
  unknown `request_id`s.
- Ensure `cancel_active_turn()` also cancels any pending approval futures
  (mark them denied / cancelled) so a `new_session` cleanly resets state.

### 7.4 Multi-turn fix (goal #4)

The most likely cause is that the web app currently treats `turn_end`
purely as "go idle" and never re-readies state for the next turn — but
`startRecording` already gates on `turnState === 'idle'`, so this
**should** work. We must reproduce first. Likely real-world causes to
investigate:

- `audio_buffer.clear()` already happens in `start_utterance`; verify no
  state on the server side (`utterance_started`, `current_format`)
  remains stale across turns.
- `AudioQueue` not draining cleanly — check `_playNext` re-entrancy after
  the queue empties (`web/src/audio.ts:94-110`).
- Browser `AudioContext` getting suspended after first playback on some
  browsers; resume on each new playback.
- The PTT button being left disabled because `turn_completed` and
  `turn_end` both fire and the second is misinterpreted (likely benign
  but worth confirming).

This is a **Phase 1 reproduction task**; fix scope is set after repro.

## 8. Phased implementation

Each phase is bite-sized and independently testable. Final TODO list will
mirror these phases in `docs/requirements/20260428_TODO_HERMES_VOICE_CONVERSATION_FLOW.md`.

### Phase 1 — Reproduce + diagnose multi-turn bug

- [ ] Add temporary debug logging to `web/src/app.ts` `handleWsJson` and
      `handleWsBinary` (one log per frame).
- [ ] Add temporary debug logging in `api/app/routes/voice.py` per
      received frame and per emitted frame.
- [ ] Manually run two consecutive PTT turns; capture logs.
- [ ] File findings as comments in this plan or as discoveries on the
      TODO; pick the smallest fix that restores 2nd-turn flow.
- [ ] Remove debug logs.

### Phase 2 — Chat log UI (transcripts only, no Hermes text yet)

- [ ] Update `web/src/types.ts`: add `ChatMessage = { role: 'user' | 'assistant', text: string, ts: number }`.
- [ ] Replace `#transcript` rendering in `web/src/ui.ts:renderApp` with
      `#chat-log` container; add `renderMessage` and `appendMessage`
      helpers.
- [ ] In `web/src/app.ts`, on `transcript` event push a user message and
      append-render it.
- [ ] Add bubble CSS (left vs right alignment, distinct background).
- [ ] Smoke-test: text from user appears as a right-aligned bubble.

### Phase 3 — Backend forwards Hermes assistant text

- [ ] In `api/app/services/pipeline.py`, accumulate the full Hermes text
      from deltas and emit one `{"event":"assistant_text","text":...,"final":true}`
      after the loop, before `turn_completed`.
- [ ] In `web/src/types.ts`, add `WsAssistantText` interface.
- [ ] In `web/src/app.ts`, on `assistant_text` push an assistant message
      and render it (left-aligned bubble).
- [ ] Smoke-test: chat bubble for Hermes appears alongside audio playback.

### Phase 4 — Active-state badge

- [ ] In `api/app/services/pipeline.py`, emit `active_state` frames at
      the right transitions (see §7.2).
- [ ] In `web/src/types.ts`, add `WsActiveState`.
- [ ] In `web/src/ui.ts`, restyle `#turn-state` (or add `#active-state`)
      as a colored pill; map states to CSS classes.
- [ ] In `web/src/app.ts`, set local state immediately on PTT for
      responsiveness; let server frames overwrite.
- [ ] Smoke-test: badge transitions cleanly across a full turn.

### Phase 5 — Discovery: command/approval event shapes

- [ ] Temporarily log every unrecognized `etype` in
      `api/app/services/hermes.py` SSE loop.
- [ ] Trigger a Hermes turn known to require tool permission (per
      Hermes upstream docs / configuration; see §10) and capture the
      `etype` + JSON shape.
- [ ] Document the discovered event names in this plan §10 and remove
      the discovery logging.

### Phase 6 — Approval protocol and UI

- [ ] Extend `services/hermes.py` to surface `approval_request` events
      with `{request_id, command, description, args}`.
- [ ] In `services/pipeline.py`, emit `approval_request`, suspend on a
      future, send the user's decision back to Hermes (mechanism per
      §10), then resume.
- [ ] In `routes/voice.py`, add `approval_response` inbound handling and
      `pending_approvals` map; cancel/deny on disconnect or new session.
- [ ] In `web/src/types.ts`, add `WsApprovalRequest`, `WsApprovalResolved`,
      `WsApprovalResponse` types.
- [ ] In `web/src/ui.ts`, add `#approval-panel` markup + show/hide
      helpers.
- [ ] In `web/src/app.ts`, queue requests, render the panel, send
      `approval_response` on click.
- [ ] Smoke-test approve and deny paths end to end.

### Phase 7 — Streaming chat (optional / nice-to-have)

- [ ] If latency feel suffers, add `assistant_text_delta` server frames
      and progressive bubble updates on the client. Skip if Phase 3 is
      good enough.

## 9. Tests and verification

### Backend

- Add unit tests under `api/tests/` (or wherever existing tests live —
  verify before authoring) covering:
  - `services/hermes.py`: parsing of an SSE fixture that includes a
    text delta, an approval_request, and `[DONE]`.
  - `services/pipeline.py`: with mocked Hermes + STT + TTS,
    - emits `assistant_text` after deltas;
    - emits `active_state` transitions in expected order;
    - on approval_request, suspends and only resumes after a future
      resolves;
    - cancels pending approvals on `cancel_active_turn`.
- Add a route test for `routes/voice.py` exercising
  `approval_response` end-to-end against a stub pipeline.

### Web

- TypeScript build: `npm run build` (and `tsc --noEmit` if a
  type-check script exists). Must pass.
- Manual smoke-test script (document in TODO):
  1. Connect, PTT a short utterance, verify user bubble + assistant
     bubble + audio + idle state.
  2. Immediately PTT a second utterance — verify same.
  3. Trigger an approval-requiring command, approve, verify continuation.
  4. Trigger again, deny, verify cancellation and idle return.

### Cross-cutting

- Run any existing repo test suites (`pytest`, web `npm run build`)
  per `docs/TODO_LIST_GUIDANCE.md` after each phase.

## 10. Risks and open questions

1. **Hermes approval event shape is unknown in this repo.** Phase 5 is a
   discovery phase; the plan reserves room to revise §5 frame shapes
   once we learn the upstream event names and payloads.
2. **Approval-response transport upstream** — does Hermes accept the
   approval over the same `responses` SSE stream (e.g. by POSTing a new
   request with the prior response id), or via a separate endpoint?
   Affects Phase 6 backend wiring.
3. **Approval timeout default** — pick a value (proposed 60s) and a
   default decision (proposed deny). Confirm with Nick.
4. **Chat history persistence** — none in this iteration. If wanted
   later, a small SQLite table keyed by `conversation_id` is the
   minimum.
5. **Streaming chat vs single final** — Phase 3 emits one final
   `assistant_text`. If the perceived lag is bad, Phase 7 adds deltas.
6. **Multiple in-flight approvals** — assume serialized; queue on the
   client. Revisit if Hermes can emit several at once.
7. **Mic permission UX** — unchanged; out of scope.

## 11. Deploy notes

- No new runtime dependencies expected on either side.
- New env var (only if §10.3 is configurable): `APPROVAL_TIMEOUT_SECONDS`
  in `api/app/config.py` with a sane default; document in any deploy
  README that already lists env vars.
- Frontend is still built and served as static assets; no change to the
  FastAPI static-mount or to the systemd / nginx setup.
- A web rebuild (`npm run build`) is required for any phase touching
  `web/src/`.
- Roll out by phase; each phase is independently shippable behind no
  feature flag (additive frames, additive UI).

## 12. Out of scope

- Mobile app (`mobile/` if present) — explicitly excluded.
- Auth / login changes.
- Persistent chat history.
- Voice activity detection / barge-in.
- Multi-user concurrency beyond what already exists.
