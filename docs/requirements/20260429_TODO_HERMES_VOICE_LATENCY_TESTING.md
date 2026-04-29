# 20260429 TODO — Hermes Voice Latency Testing Mode

Branch: `dev_02`
Implementer target: **Sonnet** (strict TDD; no Opus required)
Date (Pacific): 2026-04-29

## Goal

Make HermesVoice usable end-to-end during voice testing with Nick by relaxing
Hermes streaming timeouts, surfacing "still thinking" progress to the UI, and
rejecting clearly-degenerate audio before it reaches OpenAI STT. We must not
silently strip all safety bounds — keep timeouts, but raise them and add
distinguishable failure categories so latency logs remain useful for follow-up
tuning.

## Background

Recent diagnosis (see `/home/nick/hermesvoice_opus_latency_diagnostic_2026-04-29.md`)
shows the dominant failure mode is Hermes first-speakable-delta latency:
STT completes, then `stream_hermes_text()` may produce no
`response.output_text.delta` event for ~30 s, tripping
`HERMES_INTER_TOKEN_TIMEOUT=30` and ending the turn with an error.
Two secondary problems also appeared:

- Tiny utterances (e.g. `audio_bytes=5`) are forwarded to OpenAI STT and come
  back as `audio_too_short` / invalid, surfacing as user-visible turn errors.
- `latency.first_audio_sent` logs both `first_audio_from_turn_start_ms` and
  `first_audio_from_end_ms` from the same value, and `utterance_buffer_ms`
  is logged without clear semantics.

Phases 0–4 of the conversation flow project are merged. This TODO is
scoped to making the current pipeline robust for live testing and producing
better data for the next tuning round; it is not a rework of the streaming
architecture.

## Scope

**In scope**
- Backend Hermes timeout knobs and stream instrumentation
- Backend "still thinking" progress event during long Hermes waits
- Backend rejection of degenerate utterances pre-STT
- Latency log naming/semantics fixes (`utterance_buffer_ms`, duplicate
  `first_audio_from_end_ms`)
- Web frontend: minimal handling for the new progress event so the UI does
  not appear dead during long Hermes waits

**Deferred / out of scope**
- Mobile client work (out of scope per project rules)
- Hermes server-side performance tuning
- Replacing OpenAI STT or changing audio capture format
- Reworking the chunker or TTS pipeline
- New metrics/observability stack — keep using loguru lines

## Acceptance Criteria

The implementer can check these off when all phases are merged:

- [x] `HERMES_INTER_TOKEN_TIMEOUT` default raised, plus a separate
  first-event timeout setting; both overridable via env without code change.
- [x] `stream_hermes_text()` distinguishes "no first event from Hermes",
  "first event but no first speakable delta", and "gap between deltas",
  with separate `latency.hermes_*` log events and clear failure messages.
- [x] Backend emits at least one `active_state=thinking_progress` (or
  equivalent) frame when Hermes is silent past a configurable threshold
  while a turn is running, and the web client renders it as a non-error
  "still thinking…" indicator.
- [x] Utterances below a configurable byte / duration threshold are rejected
  before STT with a clear, non-fatal frame to the client and a structured
  log line; no OpenAI call is made.
- [x] `latency.first_audio_sent` reports a single, correctly-named field
  for time-from-end-of-utterance, and `utterance_buffer_ms` semantics are
  documented in the latency module docstring.
- [x] All new behavior covered by failing-first tests under `api/tests/`.
- [x] Existing test suite still green: `cd api && python -m pytest`.
- [ ] During a live smoke test, three consecutive normal-length utterances
  complete without HermesVoice-side errors, and a deliberate ~60 s Hermes
  stall produces a "still thinking" UI state rather than a turn error.

## Files Likely Touched

Backend
- `api/app/config.py` — new/updated timeout settings
- `api/app/services/hermes.py` — split timeouts, richer error categories,
  optional async progress hook or structured exception types
- `api/app/services/pipeline.py` — emit progress frame on long Hermes wait,
  utterance pre-validation, fix duplicate `first_audio_from_end_ms`
- `api/app/services/latency.py` — docstring/semantics for
  `utterance_buffer_ms`; possibly a new field name
- `api/app/services/stt.py` — only if pre-validation lives next to STT
- `api/tests/test_hermes_stream.py` (new)
- `api/tests/test_pipeline_progress.py` (new)
- `api/tests/test_pipeline_short_audio.py` (new)
- `api/tests/test_latency_logging.py` — adjust if field names change

Frontend (minimal)
- `web/src/...` (whichever component owns `active_state` rendering) — render
  the new progress sub-state
- A web test if the project already has one for active state; otherwise
  manual verification only

Docs
- This TODO file checked off per phase

## Test Commands

Python (always check `which python` first per repo convention):

```
cd api && python -m pytest
cd api && python -m pytest tests/test_hermes_stream.py -v
cd api && python -m pytest tests/test_pipeline_progress.py -v
cd api && python -m pytest tests/test_pipeline_short_audio.py -v
cd api && python -m pytest tests/test_latency_logging.py -v
```

Web (only if frontend changes are made):

```
cd web && npm run test --silent
cd web && npm run typecheck
```

## TDD Discipline

For every phase:
1. Write the new test(s) first. Run them; confirm they fail for the right
   reason (missing setting, missing event, missing behavior).
2. Implement the smallest change that turns the new tests green.
3. Run the full `api` suite. Fix any regressions before committing.
4. Commit per the per-phase commit guidance below.

Do not add code that is not exercised by a test in this round, except for
loguru log strings (which are exercised indirectly).

## Phases

### Phase 1 — Configurable timeouts and naming

- [x] Add settings to `api/app/config.py`:
  - `HERMES_FIRST_EVENT_TIMEOUT` (default 60s) — time from request send to
    the first SSE line of any kind
  - `HERMES_FIRST_DELTA_TIMEOUT` (default 120s) — time from first SSE line
    to the first `response.output_text.delta`
  - Raise `HERMES_INTER_TOKEN_TIMEOUT` default to 120 (gap between deltas
    once streaming has started)
  - Keep `HERMES_REQUEST_TIMEOUT` at 600
- [x] Tests in `api/tests/test_config.py` (or new) confirming defaults and
  env override.
- [x] No behavior change in `hermes.py` yet beyond reading the new settings.

### Phase 2 — Hermes stream categorized timeouts and instrumentation

- [x] In `api/tests/test_hermes_stream.py`, write tests using a fake async
  line iterator that:
  - emits no lines → expect a `RuntimeError` whose message identifies
    "first event timeout" and a `latency.hermes_first_event_timeout` log
  - emits non-delta SSE lines but no speakable delta within the window →
    expect a "first delta timeout" error and matching log
  - emits deltas with a long gap → expect inter-token timeout error
  - emits a normal stream → no error, and `latency.hermes_first_event_ms`
    log is emitted exactly once
- [x] Implement: split the single timeout check in `stream_hermes_text()`
  into the three categories; emit a structured loguru line at first raw
  event and propagate distinct `RuntimeError` messages.
- [x] Confirm existing pipeline tests still pass (the existing
  `latency.hermes_first_delta` event must remain).

### Phase 3 — Pipeline "still thinking" progress frame

- [x] In `api/tests/test_pipeline_progress.py`:
  - Patch `stream_hermes_text` with an async generator that sleeps past the
    progress threshold before yielding its first delta (use `asyncio.sleep`
    with a small monkeypatched threshold, e.g. 0.05s for the test).
  - Assert that `send_json` was called with an `active_state` frame whose
    state is `thinking_progress` (or agreed name) at least once before any
    audio is sent.
  - Assert that on a fast Hermes path the progress frame is not sent.
- [x] Implement: in `run_voice_turn` (or a small helper) start a background
  task that emits the progress frame on a configurable interval until the
  first delta arrives or the turn ends.
  - Add `HERMES_PROGRESS_INTERVAL` setting (default 8s).
  - Cancel the task on first delta, on cancellation, and in the failure
    path. No leaked tasks.
- [x] Update existing `test_pipeline_phase3` and multi-turn tests if they
  asserted an exact `active_state` sequence.

### Phase 4 — Reject degenerate utterances pre-STT

- [x] In `api/tests/test_pipeline_short_audio.py`:
  - Calling `run_voice_turn` with `audio_bytes=b""` or below a small
    threshold must NOT call `transcribe`, must send a `voice_turn_skipped`
    (or equivalent) JSON frame with a non-error reason like
    `"audio_too_short"`, must log
    `latency.turn_skipped reason=audio_too_short`, and must reset
    `active_state` to `idle`.
  - A normal-size utterance still flows through unchanged.
- [x] Implement: add `MIN_UTTERANCE_BYTES` setting (e.g. 1500) in
  `config.py`; in `run_voice_turn`, perform the check immediately after
  `latency.turn_started` and short-circuit before STT.
- [x] Confirm websocket/state tests still pass.

### Phase 5 — Latency log semantics fixes

- [x] Update `latency.first_audio_sent` to log:
  - `first_audio_from_turn_start_ms` only (drop the duplicate)
  - or, if `first_audio_from_end_ms` is meant to measure time from
    end-of-utterance, compute it from a recorded `utterance_end` mark and
    keep both, but make them genuinely distinct.
- [x] Document `utterance_buffer_ms` in the `TurnTimer` docstring: what it
  currently measures (server-observed gap between start/end utterance control
  frames, not true user speech duration) and why it can be None.
- [x] Update `api/tests/test_latency_logging.py` only as needed; add a new
  test that asserts the two latency fields, when both present, are
  different values for a synthetic turn.

### Phase 6 — Frontend "still thinking" rendering (minimal)

- [x] In the web component that already handles `active_state`, render the
  new sub-state as a visible but non-error indicator (e.g. dim spinner +
  "Hermes is taking longer than usual…"). Reuse existing styles.
- [x] If a web test exists for active-state rendering, add a case for the
  new state. Otherwise document a manual UI check in this TODO.

### Phase 7 — Live smoke test and tuning notes

- [ ] Run `python -m pytest` in `api/`; all green.
- [ ] Manual smoke test (Nick driving):
  1. Open the web client, sign in, start voice mode.
  2. Three consecutive normal-length utterances → no error frames; UI
     transitions `idle → thinking → speaking → idle` cleanly.
  3. One utterance where Hermes is forced/known to be slow (>30s, <90s)
     → `thinking_progress` indicator appears, then a normal speaking phase
     when Hermes finally responds.
  4. One deliberately tiny tap (release immediately) → no STT call,
     UI shows a non-error "didn't catch that" or returns to idle.
- [ ] Capture a fresh latency log excerpt and append observations (not
  secrets, not env contents) to a follow-up notes doc if any new tuning is
  needed. This TODO can be marked complete even if further tuning is
  identified, as long as the acceptance criteria above hold.



Implementation verification run by agent:
- 2026-04-29: `/home/limited_user/environments/hermes_voice/bin/pytest -q` → 58 passed.
- 2026-04-29: `cd web && npm run build` → passed.
- Manual live browser/voice smoke remains for Nick after service restart.

## Commit Guidance

Per `docs/CommitMessagesGuidance.md`. One commit per phase, referencing
this TODO and the phase. Examples:

```
feat: hermes timeouts split into first-event and first-delta

- references docs/requirements/20260429_TODO_HERMES_VOICE_LATENCY_TESTING.md
  Phase 2
- categorize first-event vs first-delta vs inter-token timeouts
- emit latency.hermes_first_event_ms; distinct error messages per category
```

```
feat: emit thinking_progress while waiting on hermes

- references TODO 20260429 Phase 3
- background task sends active_state=thinking_progress on a configurable
  interval; cancelled on first delta, completion, or failure
```

Do not bundle phases into a single commit. Do not push from the
implementer agent — Nick will push.

## Notes for the Implementer

- Strict TDD: failing test first, then implementation. Do not skip.
- Do not read, print, or commit `.env` values or secrets. The Hermes URL
  and key already live in settings; reference them via `settings.*` only.
- Use Pacific dates in any new doc lines (`20260429`).
- Mobile is out of scope.
- If a phase's design assumption turns out to be wrong (e.g. Hermes never
  emits any pre-delta SSE lines, so "first event timeout" is meaningless),
  stop and write a short note in this TODO under the phase rather than
  silently changing scope.
