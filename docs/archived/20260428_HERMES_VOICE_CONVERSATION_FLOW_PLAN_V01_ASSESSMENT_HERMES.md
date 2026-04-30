# HermesVoice Conversation Flow Plan V01 — Hermes Assessment

Date: 2026-04-28
Assessor: Hermes Agent
Plan assessed: `docs/20260428_HERMES_VOICE_CONVERSATION_FLOW_PLAN_V01.md`
Branch: `dev_02`

## Summary

The plan is directionally sound and should proceed to a TODO file, with one important caveat: the command/tool approval feature is only fully feasible after we confirm the Hermes API server exposes approval requests and accepts approval decisions over a machine-addressable protocol. The plan already recognizes this uncertainty in Phase 5 and §10, so the TODO should preserve that discovery gate and should not assume the final approval transport until discovery is complete.

## Vite / framework assessment

Vite is sufficient for these requested improvements. No Next.js migration is needed.

Reasons:

- The requested UI work is client-side state, DOM rendering, WebSocket events, and audio playback.
- There is no SSR, app routing, SEO, server components, or Next-specific backend need.
- The current deployment serves static web assets through FastAPI, which fits Vite well.
- Moving to Next.js would add operational complexity without solving the active problems.

## What looks good

1. **Correctly keeps scope to web + API.** The plan explicitly excludes mobile work.
2. **Correctly identifies the missing assistant text path.** Current `pipeline.py` streams Hermes deltas into TTS audio but does not send assistant text JSON frames to the browser. Adding `assistant_text` or `assistant_text_delta` frames is the right architecture for visible Hermes response bubbles.
3. **Uses additive WebSocket protocol changes.** New frames such as `assistant_text`, `active_state`, and approval frames should not break existing frame handling.
4. **Preserves Vite and the FastAPI static deployment model.** This aligns with the current avatar08/maestro04 deployment.
5. **Separates discovery from implementation for command approval.** This is necessary because the current repo does not prove the upstream Hermes permission event shape or approval response transport.
6. **Includes multi-turn diagnosis before fixing.** The user-observed possible second-turn issue should be reproduced before changing unrelated state handling.

## Required caveat / potential feasibility problem

### Command approval is not yet proven end-to-end

The plan proposes a client approval UI and an `approval_response` frame, but the current code only calls Hermes through `POST /v1/responses` and consumes SSE response events. I have not verified from the current repo that Hermes' API server:

- emits permission/approval-request events over `/v1/responses` SSE,
- includes stable request IDs and command metadata in those events,
- accepts an approval/denial response from an external API client,
- can resume the same pending agent run after approval.

Because of this, command approval is feasible as a product requirement, but Phase 6 implementation is conditional on Phase 5 discovery. If Hermes does not currently expose this externally, the fallback would be to update Hermes Agent/API server itself or add an explicit HermesVoice-side confirmation protocol for commands that HermesVoice initiates. That would be a larger cross-project change.

## Suggested TODO structure

Proceed with a TODO file, but structure it so the approval feature has a hard discovery gate:

1. Phase 0 — Baseline and tests for current multi-turn behavior.
2. Phase 1 — Chat log for user transcript bubbles.
3. Phase 2 — Backend emits assistant text and web renders Hermes bubbles.
4. Phase 3 — Active-state indicator and fluid conversation state cleanup.
5. Phase 4 — Multi-turn bug fix, if reproduced.
6. Phase 5 — Hermes tool/approval event discovery.
7. Phase 6A — Approval UI shell and protocol types, only after event shape is known.
8. Phase 6B — End-to-end approval decision transport, only if Hermes API supports it.
9. Phase 7 — Optional streaming text deltas / polish.

Each phase should include tests/build checks and commit instructions per `docs/TODO_LIST_GUIDANCE.md`.

## Minor plan improvements for the TODO

- Prefer `assistant_text_delta` earlier than optional if we want the UI to feel fluid. It can still accumulate to a final bubble, but progressive text gives better voice feedback.
- Keep debug logging controlled by a local constant or environment flag and remove it before commit.
- Add explicit tests for two consecutive turns using mocked STT/Hermes/TTS instead of relying only on manual browser testing.
- Update `docs/avatar08-api-web-runbook.md` if new env vars such as `APPROVAL_TIMEOUT_SECONDS` are introduced.
- For approval timeouts, defaulting to deny is appropriate unless Nick requests otherwise.

## Recommendation

Proceed to create the TODO file, with the approval implementation represented as discovery-gated phases rather than guaranteed implementation details. The plan is good enough to guide the next work cycle and does not require a framework change.
