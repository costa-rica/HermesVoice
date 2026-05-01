# TODO: Hermes Voice Conversational Responses

**Date:** 2026-04-29  
**Branch:** dev_02

## Goal

Make HermesVoice responses better suited for voice conversation by passing a `source` and `instructions` context to Hermes on every turn.

---

## Phase 1: Payload construction and pipeline wiring

- [x] Add `VOICE_INSTRUCTIONS` constant to `api/app/services/hermes.py`
- [x] Add optional `source` and `instructions` keyword args to `stream_hermes_text()`; include in payload only when non-None
- [x] Add optional `source` and `instructions` to `_chunk_hermes_text()` and pass through to `stream_hermes_text()`
- [x] In `run_voice_turn()`, call `_chunk_hermes_text` with `source="voice"` and `instructions=VOICE_INSTRUCTIONS`
- [x] Update existing pipeline test fakes to accept `**kwargs` for backward compatibility
- [x] Add tests: payload includes source/instructions when provided, omits by default
- [x] Add tests: pipeline passes `source="voice"` and `VOICE_INSTRUCTIONS` to Hermes
- [x] All 68 tests pass

---

## Phase 2: Schema compatibility validation (manual)

The `source` and `instructions` fields are injected into the Hermes `/responses` payload. Whether Hermes accepts or silently ignores these fields must be validated manually against a live instance.

**Remaining manual check:**
- [ ] Send a request with `source="voice"` and `instructions="..."` to the live Hermes `/responses` endpoint and confirm HTTP 200 (not 400 unknown-field error).
- [ ] If Hermes rejects unknown fields (HTTP 400), implement a controlled prefix strategy (prepend instructions as a preamble to `input`) and add a narrowly-scoped test.

> No production fallback was added at this stage — schema rejection would surface clearly in logs as `Hermes returned HTTP 400`.

---

## Phase 3: Tuning (future)

- [ ] Evaluate voice response quality in a real conversation session
- [ ] Refine `VOICE_INSTRUCTIONS` wording based on observed output
- [ ] Consider per-conversation override for non-voice (API) callers if needed
