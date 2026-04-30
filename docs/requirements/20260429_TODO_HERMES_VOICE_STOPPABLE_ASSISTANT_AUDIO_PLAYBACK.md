# 20260429 TODO — Hermes Voice Stoppable Assistant Audio Playback

Branch: `dev_03`
Implementer target: **strict TDD**
Date (Pacific): 2026-04-29

## Goal

Fix the browser-side cancellation gap where assistant audio can keep playing after
the user presses cancel once audio has already been released to the browser.

Current behavior is grounded in the frontend code:
- `web/src/audio.ts` `AudioQueue.clear()` only empties queued `Blob`s. It does
  not stop an already-started `AudioBufferSourceNode`.
- `web/src/app.ts` `sendCancelTurn()` sends `cancel_turn` and optimistically
  sets the local turn state to `idle`, but does not stop active local playback.
- `web/src/app.ts` `handleWsBinary()` enqueues every binary frame, so late audio
  frames arriving after cancel can start or continue assistant playback.

The fix should be local and client-side: pressing cancel must immediately stop
any already-released assistant audio, clear pending browser-side audio, and guard
against late audio frames from the canceled turn until the next user utterance or
new assistant turn is clearly allowed.

## Scope

**In scope**
- Add stoppable playback behavior to `AudioQueue` for audio that is already
  decoded and playing in the browser.
- Update `App` cancel handling to stop local playback immediately when
  `cancel_turn` is sent.
- Add a client-side cancellation guard so binary audio frames that arrive after
  cancel are ignored while the local turn is canceled/idle.
- Reset the guard when a new user recording starts, and when server state
  indicates a legitimate new assistant turn can play.
- Add focused Vitest coverage for audio queue stopping and app-level late-frame
  suppression.

**Out of scope**
- Backend cancellation changes.
- Changes to WebSocket protocol shape unless existing frames are insufficient.
- TTS generation, server buffering, auth, reconnect/heartbeat behavior, or UI
  layout changes beyond using the existing cancel button behavior.
- Mobile / Flutter clients.

## Acceptance Criteria

- [ ] Pressing cancel while assistant audio is currently playing stops the active
  browser `AudioBufferSourceNode` immediately.
- [ ] Pressing cancel clears queued assistant audio that has not started yet.
- [ ] Pressing cancel still sends exactly one `{ "event": "cancel_turn" }`
  frame over the existing WebSocket path.
- [ ] Binary audio frames that arrive after local cancel are ignored and are not
  enqueued for playback.
- [ ] Starting a new user recording resets the local audio-cancel guard so the
  next turn can play audio normally.
- [ ] Normal assistant audio playback remains sequential for non-canceled turns.
- [ ] Decode failures continue to skip bad chunks and advance to later queued
  chunks.
- [ ] All new behavior is covered by failing-first Vitest tests.
- [ ] `cd web && npm test -- --run` passes.
- [ ] `cd web && npm run build` passes.

## Files Likely Touched

Frontend implementation
- `web/src/audio.ts` — track the active `AudioBufferSourceNode`; make
  `clear()` stop active playback, clear queued blobs, and prevent stale
  `onended` handlers from advancing playback after cancellation.
- `web/src/app.ts` — call `audioQueue.clear()` from `sendCancelTurn()`; add a
  local cancellation guard checked by `handleWsBinary()`; reset the guard from
  `startRecording()` and from relevant server state transitions.

Frontend tests
- `web/src/__tests__/audio-queue.test.ts` (new) — unit tests for active-source
  stopping, queue clearing, stale `onended` handling, and sequential playback.
- `web/src/__tests__/assistant-audio-cancel.test.ts` (new) — app-level tests for
  cancel sending, immediate `AudioQueue.clear()`, late binary frame suppression,
  and guard reset on the next recording.
- Existing tests may need mock updates if `AudioQueue` gains a `stop()` alias or
  stricter clear semantics:
  - `web/src/__tests__/connection-status-ux.test.ts`
  - `web/src/__tests__/heartbeat-lifecycle.test.ts`

Docs
- This TODO file only.

## TDD Discipline

For every implementation phase:
1. Write the new failing test(s) first.
2. Run the narrow test command and confirm the failure is for the expected
   missing behavior.
3. Implement the smallest code change that makes the new test pass.
4. Run the full web test suite and build command listed for the phase.
5. Check off the phase only after verification passes.
6. Commit per `docs/CommitMessagesGuidance.md`, referencing this TODO file and
   the completed phase.

## Phases

### Phase 1 — AudioQueue can stop active browser playback

- [ ] Create `web/src/__tests__/audio-queue.test.ts`.
- [ ] Mock `AudioContext`, `decodeAudioData`, `createBufferSource`,
  `connect()`, `start()`, `stop()`, and `onended` so playback behavior is
  deterministic under jsdom.
- [ ] Write failing tests proving current behavior:
  - `clear()` empties queued chunks and calls `stop()` on the currently playing
    source.
  - A stopped source's later `onended` callback does not start stale queued
    audio.
  - Normal, non-canceled playback still advances from first chunk to second
    chunk when `onended` fires.
  - Decode errors still skip the bad chunk and continue to the next queued chunk.
- [ ] Run narrow failing test:
  - `cd web && npm test -- --run src/__tests__/audio-queue.test.ts`
- [ ] Update `web/src/audio.ts`:
  - Add an `activeSource` field for the currently started
    `AudioBufferSourceNode`.
  - Add a playback generation/token field so `clear()` invalidates in-flight
    decode/start work and stale `onended` handlers.
  - In `clear()`, empty `queue`, stop and disconnect the active source if
    present, clear `activeSource`, and set `playing = false`.
  - In `_playNext()`, only start or advance playback if the generation still
    matches.
- [ ] Re-run:
  - `cd web && npm test -- --run src/__tests__/audio-queue.test.ts`
  - `cd web && npm test -- --run`
  - `cd web && npm run build`

### Phase 2 — Cancel button stops local playback immediately

- [ ] Create `web/src/__tests__/assistant-audio-cancel.test.ts`.
- [ ] Reuse the existing app test style: mock `../ui`, mock `../audio`, and use
  a controllable `WebSocket` test double.
- [ ] Write failing tests proving current behavior:
  - Clicking `#btn-cancel` sends one `cancel_turn` JSON frame.
  - Clicking `#btn-cancel` calls `AudioQueue.clear()` immediately, even before
    any server `active_state=idle` confirmation.
  - The local turn state is optimistically set back to `idle`.
- [ ] Run narrow failing test:
  - `cd web && npm test -- --run src/__tests__/assistant-audio-cancel.test.ts`
- [ ] Update `web/src/app.ts` `sendCancelTurn()`:
  - Keep the existing WebSocket `cancel_turn` send.
  - Call `this.audioQueue.clear()` before or immediately after sending cancel.
  - Set a local audio-canceled guard used by Phase 3.
  - Preserve the optimistic `setTurnState('idle')`.
- [ ] Re-run:
  - `cd web && npm test -- --run src/__tests__/assistant-audio-cancel.test.ts`
  - `cd web && npm test -- --run`
  - `cd web && npm run build`

### Phase 3 — Ignore late audio frames after cancel

- [ ] Extend `web/src/__tests__/assistant-audio-cancel.test.ts` with failing
  tests:
  - After cancel, a later binary WebSocket frame does not call
    `AudioQueue.enqueue()`.
  - Starting a new recording clears the local audio-canceled guard.
  - After the guard is reset, a binary frame from the next legitimate turn is
    enqueued normally.
  - Reconnect/close cleanup still clears audio and leaves the app able to accept
    a future session.
- [ ] Run the narrow tests and confirm expected failures:
  - `cd web && npm test -- --run src/__tests__/assistant-audio-cancel.test.ts`
- [ ] Update `web/src/app.ts`:
  - Add a private boolean such as `suppressAssistantAudio`.
  - Set it to `true` in `sendCancelTurn()`.
  - In `handleWsBinary()`, return without updating first-audio timings or
    calling `enqueue()` when suppression is active.
  - Reset it in `startRecording()` before beginning a new utterance.
  - Reset it when a new valid assistant playback phase begins if the existing
    server events make that unambiguous; prefer `active_state` transitions over
    timing assumptions.
  - Keep `triggerReconnect()` and `handleWsClose()` clearing local playback.
- [ ] Re-run:
  - `cd web && npm test -- --run src/__tests__/assistant-audio-cancel.test.ts`
  - `cd web && npm test -- --run`
  - `cd web && npm run build`

### Phase 4 — Regression hardening and final verification

- [ ] Review and update existing mocked `AudioQueue` shapes in:
  - `web/src/__tests__/connection-status-ux.test.ts`
  - `web/src/__tests__/heartbeat-lifecycle.test.ts`
- [ ] Add any missing regression test from implementation findings, especially
  around stale async `decodeAudioData()` completion after cancel.
- [ ] Run final verification:
  - `cd web && npm test -- --run`
  - `cd web && npm run build`
- [ ] Manually smoke test in a browser:
  1. Start a long assistant response.
  2. Wait until audio is audibly playing.
  3. Press cancel.
  4. Confirm audio stops immediately and does not resume from late frames.
  5. Start a new utterance and confirm assistant audio plays normally.
- [ ] Check off all acceptance criteria above.

## Implementation Notes

- `AudioBufferSourceNode.stop()` can throw if the source has already stopped in
  some browsers. Wrap stop/disconnect cleanup defensively so cancel remains
  best-effort and idempotent.
- Keep the public `AudioQueue.clear()` API if possible because existing app code
  already uses it on start, close, and reconnect. If a separate `stop()` method
  is added, have `clear()` delegate to the same stop-and-discard behavior so old
  call sites remain safe.
- Guarding late frames in `App` is intentionally separate from stopping
  `AudioQueue`: `clear()` handles audio already released to the browser, while
  the app-level guard prevents canceled server output from being released later.
- Do not update first-audio latency timing for frames ignored after cancel.

## Commit Guidance

Use `docs/CommitMessagesGuidance.md`. One commit per completed phase is
preferred.

```
test: cover stoppable assistant audio queue

- refs 20260429_TODO_HERMES_VOICE_STOPPABLE_ASSISTANT_AUDIO_PLAYBACK.md Phase 1
- add failing-first coverage for stopping active browser playback
```

```
fix: stop assistant audio on cancel

- refs 20260429_TODO_HERMES_VOICE_STOPPABLE_ASSISTANT_AUDIO_PLAYBACK.md Phase 2
- cancel now clears active and queued browser-side assistant audio
```

```
fix: ignore late audio frames after cancel

- refs 20260429_TODO_HERMES_VOICE_STOPPABLE_ASSISTANT_AUDIO_PLAYBACK.md Phase 3
- suppress canceled binary audio until the next valid turn
```
