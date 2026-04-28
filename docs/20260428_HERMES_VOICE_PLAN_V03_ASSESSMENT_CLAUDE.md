# Assessment of HERMES_VOICE_PLAN_V03

**Reviewer:** Claude (Opus 4.7)
**Date:** 2026-04-28
**Subject:** [docs/20260428_HERMES_VOICE_PLAN_V03.md](20260428_HERMES_VOICE_PLAN_V03.md)

The plan is coherent and the web-first pivot is sound: a browser harness on the same host as Hermes is the cheapest way to prove the WebSocket contract before paying the Flutter/Xcode tax. The directory layout, env model, systemd unit, and Nginx-terminates-TLS pattern are all conventional and fine. What follows is only the set of items I think materially affect success.

---

## Fatal / near-fatal concerns

### 1. Browser mic capture requires HTTPS — phase ordering is wrong

`getUserMedia` (and therefore `MediaRecorder`) only works in a **secure context**. The exceptions are `localhost` and `127.0.0.1`. Phase 5 ("Web validation client") is scheduled *before* Phase 6 ("Ubuntu deployment / Nginx TLS"). That means:

- You can develop the web client locally against `localhost:8700` and it will work.
- The moment you test it against `avatar08`'s LAN IP or a hostname over plain HTTP, the mic API silently refuses and the harness looks broken for the wrong reason.

**Fix:** either (a) move TLS / public URL provisioning into Phase 4-5 so the *first* end-to-end test of the web client happens over HTTPS, or (b) explicitly mandate that all Phase-5 testing is done from a browser on the Ubuntu box itself against `localhost`. The plan currently implies neither and that ambiguity will burn an afternoon.

### 2. Audio format contract on the WebSocket is underspecified

The plan says inbound frames are "binary audio chunks plus JSON control frames" and acknowledges the web client may produce `webm/opus` while mobile sends WAV. But the backend has to hand bytes to Whisper, and Whisper needs a filename/extension or content-type to sniff the container. There is no description of how the server learns which codec it just received.

This is the single biggest interop hazard. **Fix:** require a JSON metadata frame at turn start, e.g.

```json
{"event":"start_utterance","format":"webm/opus","sample_rate":48000}
```

…and reject turns where format wasn't declared. Without this, every codec change is a debugging session.

### 3. TTS "streaming" plan is hand-wavy — this is the latency story

The plan says "as soon as Hermes emits usable text deltas, the backend batches them into TTS-friendly chunks and streams audio back." OpenAI's `tts-1` is **not a streaming model** in the SSE sense — each request returns one audio blob. To get the perceived-streaming behavior the plan promises, you have to:

1. Detect sentence/clause boundaries in the Hermes delta stream.
2. Fire a TTS request per chunk.
3. Concatenate Opus frames on the wire (Opus is forgiving here, but you still need to think about page boundaries if using OGG-Opus vs raw Opus).
4. Decide what to do when Hermes emits a 600-token sentence with no punctuation.

None of this is in the plan. It's the part most likely to feel bad in V1. **Fix:** write a one-page sub-design for the pipeline coordinator before Phase 3, including the chunking heuristic and a worst-case "no punctuation in N seconds, force-flush" rule. Also evaluate `gpt-4o-mini-tts` — it has materially lower TTFB than `tts-1` and the env already treats `TTS_MODEL` as configurable.

---

## Things I'd do differently (significant uplift, not fatal)

### 4. Pick the web stack now, and make it boring

`web/package.json` is listed but no framework is chosen. For a validation harness — single page, one button, a transcript pane, a WebSocket — **vanilla TS + Vite** will be done in a day. React/Svelte/etc. add a build pipeline you don't need. The plan's stated purpose ("validation harness, not a second product") argues for the smallest possible footprint. State that explicitly so future-you doesn't reach for Next.

### 5. Cancellation must be designed in Phase 4, not deferred to Phase 9

The plan says "ignore [interrupts] during V1, but structure turns as cancellable tasks." Fine in principle, but the only mechanism mentioned is `new_session`, which clears buffered audio. What happens if `new_session` arrives while TTS is mid-stream on a previous turn? You need:

- A per-turn `asyncio.Task` for the STT→Hermes→TTS pipeline.
- A cancel path triggered by `new_session` *or* socket disconnect that aborts the in-flight Hermes SSE read and any pending TTS request.
- A guarantee that no audio bytes from a cancelled turn are written to the socket after cancel.

Without this, "ignore interrupts" turns into "two voices talking over each other after a reconnect."

### 6. Public web login needs minimal abuse protection

A single shared password served on the public internet with no rate limiting will get probed. At minimum:

- Rate-limit `/login` (e.g. `slowapi` or Nginx `limit_req`).
- Lock out per-IP after N failures for M minutes.
- Set `HttpOnly; Secure; SameSite=Lax` on the session cookie (worth stating in the plan).
- Consider a long random URL prefix or basic-auth shield in Nginx as defense-in-depth until the API-key path lands.

This is cheap and prevents a class of incidents the plan doesn't acknowledge.

### 7. `HERMES_REQUEST_TIMEOUT=600` + no idle cap = hung turns

Ten minutes is a long time to wait for a stuck SSE stream with no interrupt path. Add an **inter-token idle timeout** (e.g. "abort if no Hermes delta for 30s") separate from the overall request timeout. Same for TTS. The user-visible failure mode without this is "the app froze," which is the worst possible class of bug for a voice product.

### 8. Logging path needs a deploy-time prerequisite

`PATH_TO_LOGS=/var/log/hermes-voice` requires root to create and chown to `limited_user`. Either:

- Switch to systemd `LogsDirectory=hermes-voice` (creates `/var/log/hermes-voice` with correct ownership automatically), or
- Add an explicit pre-deploy step to Phase 6 ("create and chown log dir").

As written, the first `systemctl start` will crash on a permission error and the failure won't be obvious from `journalctl` if logging itself is broken.

### 9. `.env` permissions and secret hygiene

The env file holds `OPENAI_API_KEY`, `HERMES_API_KEY`, `SESSION_SECRET`, and the web password. Plan should specify `chmod 600` and `chown limited_user:limited_user` on `.env`, and that systemd's `EnvironmentFile=` reads it as root before dropping privileges (so 600 is fine). Worth one line.

### 10. Conversation ID lifecycle is implicit

The plan says Hermes owns conversation state via `conversation=<session_id>`, but doesn't say where the backend gets `session_id` from, how long it lives, or whether browser refresh starts a new one. Suggest: the backend mints `conversation_id` on WS connect, returns it in a `session_started` frame, and re-uses it across turns until `new_session` or disconnect. State this explicitly.

### 11. Reconnect behavior

WS will drop. Mobile especially. The plan has no client reconnect policy and no server-side "resume conversation" behavior. For V1 it's acceptable to say "drop = new session, user must press talk again," but say it. Otherwise the web harness will accidentally invent its own behavior and the mobile app will invent a different one.

---

## Smaller notes

- Phase 0 mentions the smoke tests already passed for Whisper WAV + OGG-Opus. Good — keep those scripts in `scripts/` checked in so regressions are catchable.
- The `tts-1` choice is fine for a baseline but worth a Phase-9 line item: re-evaluate against newer TTS models for first-audio latency.
- `IDLE_TIMEOUT=120` is referenced in `.env.example` but not mentioned in the WS contract — define what it gates (socket idle? mid-turn silence?).
- The `mobile/README.md` placeholder is the right call. Resist the urge to scaffold Flutter on the Linux box.
- "Web app may use webm/opus" + "UPLINK_FORMAT=wav" together imply two code paths in `stt.py`. Make sure the service accepts either and isn't gated on the env var.

---

## Overall

No single item here is a project-killer, but **#1 (HTTPS-before-mic), #2 (codec metadata frame), and #3 (TTS chunking design)** are the three I'd resolve before writing pipeline code. The rest are quality-of-life and can be folded in as you go. The plan's biggest strength is the deliberate separation of "prove the contract on the web" from "ship the iOS app" — that's the right call and worth defending against scope drift.
