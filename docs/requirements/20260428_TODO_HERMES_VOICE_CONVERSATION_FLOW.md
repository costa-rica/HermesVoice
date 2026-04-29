# TODO — HermesVoice Conversation Flow

Date: 2026-04-28
Branch: `dev_02`
Scope: web client (`web/`) + FastAPI backend (`api/`). **Mobile app is not in scope and no mobile work is promised by this TODO.**

Source documents:

- `docs/20260428_HERMES_VOICE_CONVERSATION_FLOW_PLAN_V01.md`
- `docs/20260428_HERMES_VOICE_CONVERSATION_FLOW_PLAN_V01_ASSESSMENT_HERMES.md`

This TODO follows `docs/TODO_LIST_GUIDANCE.md`: phases are discrete, testable units; after each phase, run the relevant checks (backend `pytest`, web `npm run build`), check off completed items only after checks pass, then commit referencing this file and the phase.

---

## Build Mandate

- **Vite + vanilla TypeScript remains sufficient.** Do not migrate to Next.js.
- A Next.js (or other framework) migration is **not planned** unless a future requirement explicitly needs SSR, multi-page routing, or React Server Components. None of the work in this TODO needs any of those.
- The web client continues to build to static assets and is served by FastAPI. No new toolchain is to be introduced.
- Keep the existing module split (`app.ts` / `ui.ts` / `ws.ts` / `audio.ts` / `types.ts`). New work is additive.

## Critical Caveat (preserved from Hermes assessment)

**Command/tool approval implementation is discovery-gated.** The Hermes API approval event shape and the transport for sending an approval/deny decision back to Hermes have **not yet been proven from this repo**. Phase 5 is a discovery phase; Phase 6A and 6B may only proceed once the upstream event names, payload shapes, and response transport are confirmed. If Hermes does not currently expose approval requests externally with a stable, addressable response channel, Phase 6B is blocked and must be escalated as a cross-project change rather than implemented speculatively.

## Acceptance Criteria

The work in this TODO is complete when **all** of the following hold:

1. **Multi-turn reliability** — The user can run at least three consecutive PTT turns in a single session without reload, re-handshake, or manual intervention. Each turn produces transcript, assistant text, and audio. Verified by an automated backend test exercising two consecutive turns end-to-end against mocked STT/Hermes/TTS, plus a manual three-turn browser smoke test.
2. **Visible user and Hermes text bubbles** — Every completed turn renders a user bubble (right-aligned) from the `transcript` frame and a Hermes bubble (left-aligned) from the `assistant_text` frame, retained in a scrollable chat log for the session.
3. **Active-state indicator** — A single visible indicator transitions through `idle → listening → thinking → speaking → idle` (and `awaiting_approval` once Phase 6 is feasible) for every turn, driven by `active_state` frames with a local PTT-press fallback for responsiveness.
4. **Approval discovery and (conditional) implementation** —
   - Phase 5 **must** produce a documented record of upstream Hermes approval/tool event names and shapes (or a documented finding that they are not currently exposed).
   - Phase 6A is acceptable as a UI-only shell behind a feature gate if Phase 5 confirms shapes but Phase 6B transport remains unproven.
   - Phase 6B is only complete when an approve and a deny path each round-trip end-to-end against a real (not stubbed) Hermes turn that requires approval.

---

## Phase 0 — Baseline tests for current multi-turn behavior

Files likely touched:

- `api/tests/` (new test file, e.g. `api/tests/test_pipeline_multiturn.py`)
- `api/tests/conftest.py` (only if shared fixtures are needed)

Tasks:

- [x] Locate or create the backend test directory and confirm the test runner (`pytest`) configuration.
- [x] Add a baseline test that drives `services/pipeline.py` through one mocked turn (mocked STT, Hermes, TTS) and asserts the current frame sequence.
- [x] Add a second baseline test that drives **two consecutive turns** through the same pipeline instance / connection and records what currently happens (pass or fail). The test is allowed to xfail if the second turn is broken — the goal is a reproducible signal.
- [x] Document any reproduction details discovered (purely as a brief note in this TODO, no separate doc).

**Phase 0 findings (2026-04-29):** `run_voice_turn` is a pure function and both single-turn and two-turn tests pass on the first try — the pipeline itself is stateless between calls. A third test (`test_stale_turn_id_suppresses_output`) confirmed the cancellation guard works correctly: advancing `get_active_turn_id()` after STT (using `asyncio.sleep(0)` to guarantee interleaving) prevents audio and `turn_completed` from being emitted for the superseded turn. The multi-turn bug, if present, is likely at the WebSocket state-management layer (`voice.py`) or client-side; no pipeline fix is needed from Phase 0. The `pytest` venv is `/home/limited_user/environments/hermes_voice/bin/pytest`.

Checks:

- [x] Backend: `pytest` passes (28/28, no xfail needed).
- [x] Web: not applicable.
- [x] Update checkboxes above only after checks pass.
- [x] Commit referencing this TODO file and Phase 0.

## Phase 1 — Chat log UI for user transcripts

Files likely touched:

- `web/src/types.ts`
- `web/src/ui.ts`
- `web/src/app.ts`
- `web/src/style.css` (or co-located CSS — whichever the project already uses)
- `web/index.html` (only if markup root needs adjustment)

Tasks:

- [ ] Add `ChatMessage = { role: 'user' | 'assistant', text: string, ts: number }` to `web/src/types.ts`.
- [ ] Replace `#transcript` rendering in `web/src/ui.ts` with a `#chat-log` flex column container; add `renderMessage` and `appendMessage` helpers.
- [ ] In `web/src/app.ts`, maintain a `messages: ChatMessage[]` array and append a user bubble on every `transcript` frame.
- [ ] Add bubble CSS: `.bubble-user` right-aligned, `.bubble-assistant` left-aligned, distinct backgrounds.
- [ ] Auto-scroll the chat log to the bottom on append.

Checks:

- [ ] Backend: not applicable.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: a PTT turn produces a right-aligned user bubble.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 1.

## Phase 2 — Backend emits assistant text; web renders Hermes bubbles

Files likely touched:

- `api/app/services/hermes.py`
- `api/app/services/pipeline.py`
- `api/tests/` (new/updated tests)
- `web/src/types.ts`
- `web/src/app.ts`

Tasks:

- [ ] In `api/app/services/pipeline.py`, accumulate the full Hermes text from deltas during a turn and emit one `{"event":"assistant_text","text":...,"final":true}` frame after the delta loop and before `turn_completed`.
- [ ] (Optional refactor, if cheap) Introduce `stream_hermes_events` in `api/app/services/hermes.py` yielding tagged events, with `stream_hermes_text` retained as a thin wrapper. Skip if Phase 2 can land cleanly without it.
- [ ] Add `WsAssistantText` to `web/src/types.ts`.
- [ ] In `web/src/app.ts`, on `assistant_text` push an assistant `ChatMessage` and render a left-aligned bubble.
- [ ] Add a backend test that asserts an `assistant_text` frame is emitted with the concatenated text after a mocked Hermes delta sequence.

Checks:

- [ ] Backend: `pytest` passes.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: a PTT turn now shows both a user bubble and a Hermes bubble alongside audio playback.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 2.

## Phase 3 — Active-state indicator and fluid conversation state cleanup

Files likely touched:

- `api/app/services/pipeline.py`
- `api/tests/` (updated tests)
- `web/src/types.ts`
- `web/src/ui.ts`
- `web/src/app.ts`
- `web/src/style.css`

Tasks:

- [ ] In `api/app/services/pipeline.py`, emit `{"event":"active_state","state":...}` frames at: `thinking` (after STT completes), `speaking` (on first audio chunk), and `idle` (on turn end). Do **not** yet emit `awaiting_approval`; that arrives in Phase 6.
- [ ] Add `WsActiveState` to `web/src/types.ts` with the state union (`idle | listening | thinking | speaking | awaiting_approval`).
- [ ] In `web/src/ui.ts`, replace/augment the existing `#turn-state` text with a colored pill/badge; map states to CSS classes (idle neutral, listening green pulse, thinking amber, speaking blue, awaiting_approval red).
- [ ] In `web/src/app.ts`, set local state to `listening` immediately on PTT press for responsiveness; let server frames overwrite.
- [ ] Audit and clean any state that does not reset cleanly between turns (server `current_format`, client `AudioContext` resume, PTT button enabled state). This is the lightweight fluid-flow cleanup; the targeted multi-turn fix is Phase 4.
- [ ] Update or add a backend test asserting the `active_state` transition order for one mocked turn.

Checks:

- [ ] Backend: `pytest` passes.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: badge transitions cleanly across a full turn.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 3.

## Phase 4 — Multi-turn bug fix (if reproduced)

Files likely touched:

- `api/app/routes/voice.py`
- `api/app/services/pipeline.py`
- `web/src/audio.ts`
- `web/src/app.ts`
- `api/tests/test_pipeline_multiturn.py`

Tasks:

- [ ] Re-run the Phase 0 two-turn baseline test. If it now passes (because Phase 2/3 cleanups fixed it), convert any xfail to a passing assertion and skip the remaining bullets.
- [ ] If still failing, narrow the cause via temporary, locally-gated debug logging (constant or env flag) in `web/src/app.ts` `handleWsJson`/`handleWsBinary` and per inbound/emitted frame in `api/app/routes/voice.py`. Reproduce two consecutive PTT turns and capture the divergence.
- [ ] Apply the smallest fix that restores second-turn flow. Likely candidates: stale server `utterance_started` / `current_format`, `AudioQueue` re-entrancy after drain, suspended `AudioContext` not resumed on subsequent playback, or a misinterpreted second-fire of `turn_completed`/`turn_end`.
- [ ] Remove the temporary debug logging before commit.
- [ ] Promote the Phase 0 two-turn test from xfail (if any) to a hard assertion. Add a third-turn assertion if cheap.

Checks:

- [ ] Backend: `pytest` passes, including the two-turn (and ideally three-turn) test.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: three consecutive PTT turns succeed in the browser without reload.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 4.

## Phase 5 — Hermes tool/approval event discovery (gate for Phase 6)

Files likely touched:

- `api/app/services/hermes.py` (temporary discovery logging, removed before commit)
- `docs/20260428_HERMES_VOICE_CONVERSATION_FLOW_PLAN_V01.md` §10 (findings appended)

Tasks:

- [ ] Add temporary, locally-gated logging in the Hermes SSE loop (`api/app/services/hermes.py`) that records every unrecognized `etype` and its payload shape. Logging must be guarded by a local constant or env flag.
- [ ] Configure or trigger a Hermes turn known to require tool/command permission (per Hermes upstream configuration) and capture the `etype` plus JSON shape of any approval-request and approval-response events.
- [ ] Confirm whether Hermes accepts an approval/denial decision from an external API client, and over what transport (same `/v1/responses` SSE channel via a follow-up POST keyed by response id, or a separate endpoint).
- [ ] Document findings — event names, payload shapes, response transport, and any blockers — in §10 of the plan document. If approval is **not** externally addressable, mark Phase 6B as blocked and escalate; do **not** speculatively implement.
- [ ] Remove the discovery logging.

Checks:

- [ ] Backend: `pytest` passes (no functional changes expected).
- [ ] Web: not applicable.
- [ ] Update checkboxes above only after checks pass and discovery findings are written down.
- [ ] Commit referencing this TODO file and Phase 5.

## Phase 6A — Approval protocol types and UI shell (only if Phase 5 confirms event shapes)

**Gate:** proceed only if Phase 5 produced a confirmed approval-request event shape. If Phase 5 found no externally addressable approval flow, skip Phase 6A and 6B entirely and record that decision in this TODO.

Files likely touched:

- `web/src/types.ts`
- `web/src/ui.ts`
- `web/src/app.ts`
- `web/src/style.css`
- `api/app/services/pipeline.py` (emit `awaiting_approval` active_state, emit `approval_request` from a stub or real source — feature-gated)

Tasks:

- [ ] Add `WsApprovalRequest`, `WsApprovalResolved`, `WsApprovalResponse` to `web/src/types.ts`, matching the shapes confirmed in Phase 5.
- [ ] Add `#approval-panel` markup in `web/src/ui.ts` with show/hide helpers, an Approve button, a Deny button, and slots for `description`, `command`, and optional `args`.
- [ ] In `web/src/app.ts`, queue inbound approval requests, render one at a time, send `approval_response` on click, and locally hide on click while still treating server `approval_resolved` as authoritative.
- [ ] Wire `awaiting_approval` into the active-state badge (red highlight) added in Phase 3.
- [ ] Behind a server-side feature flag, allow `pipeline.py` to emit a synthetic `approval_request` for UI testing; the real wiring is Phase 6B.

Checks:

- [ ] Backend: `pytest` passes.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: synthetic approval request renders the panel; Approve and Deny each dismiss it and surface a `approval_response` outbound frame.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 6A.

## Phase 6B — End-to-end approval decision transport (only if Phase 5 confirms transport)

**Gate:** proceed only if Phase 5 confirmed a working transport for sending approval decisions back to Hermes and resuming the suspended turn. Otherwise this phase is blocked.

Files likely touched:

- `api/app/services/hermes.py`
- `api/app/services/pipeline.py`
- `api/app/routes/voice.py`
- `api/app/config.py` (only if `APPROVAL_TIMEOUT_SECONDS` is added)
- `api/tests/`
- `docs/avatar08-api-web-runbook.md` (only if a new env var is added)

Tasks:

- [ ] In `api/app/services/hermes.py`, surface real `approval_request` events with `{request_id, command, description, args}` per Phase 5 findings.
- [ ] In `api/app/services/pipeline.py`, emit `approval_request` to the client, set `active_state` to `awaiting_approval`, suspend on a `Future` keyed by `request_id`, send the user's decision back to Hermes via the confirmed transport, then resume the turn.
- [ ] In `api/app/routes/voice.py`, add `approval_response` to the inbound JSON dispatch and maintain a per-connection `pending_approvals: dict[str, asyncio.Future]`. Cancel/deny pending approvals on disconnect, on `cancel_active_turn`, and on `new_session`.
- [ ] Add `APPROVAL_TIMEOUT_SECONDS` (proposed default 60s, default decision deny) to `api/app/config.py`. On timeout emit `approval_resolved` with `decision: "denied"`. Document the env var in `docs/avatar08-api-web-runbook.md`.
- [ ] Add backend tests covering: pipeline suspends on `approval_request`, resumes after `approval_response`, denies on timeout, and cancels pending approvals on `cancel_active_turn` and disconnect.
- [ ] Remove any synthetic-approval feature flag added in Phase 6A.

Checks:

- [ ] Backend: `pytest` passes, including the new approval tests.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: against a real Hermes turn that requires approval, both approve and deny paths round-trip end-to-end and the turn resumes (or aborts) correctly.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 6B.

## Phase 7 — Optional: streaming chat deltas

Files likely touched:

- `api/app/services/pipeline.py`
- `web/src/types.ts`
- `web/src/app.ts`

Tasks:

- [ ] If perceived latency on Hermes bubbles is poor after Phase 2, add `assistant_text_delta` server frames and progressive bubble updates on the client, accumulating into the same final `assistant_text` bubble.
- [ ] Skip this phase entirely if Phase 2's single-final bubble feels acceptable.

Checks:

- [ ] Backend: `pytest` passes.
- [ ] Web: `npm run build` succeeds.
- [ ] Manual smoke: progressive bubble update is smooth and ends in the same final text as before.
- [ ] Update checkboxes above only after checks pass.
- [ ] Commit referencing this TODO file and Phase 7.

---

## Out of scope (explicit)

- Mobile app work of any kind.
- Auth / login changes.
- Persistent chat history (browser-memory only for this iteration).
- Voice activity detection / barge-in.
- Multi-user concurrency beyond what already exists.
- Any framework migration (Next.js or otherwise) — see Build Mandate above.
