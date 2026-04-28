# Assessment of TODO_HERMES_VOICE (V04)

**Reviewer:** Claude (Opus 4.7)
**Date:** 2026-04-28
**Subject:** [docs/requirements/20260428_TODO_HERMES_VOICE.md](20260428_TODO_HERMES_VOICE.md)
**Source plan:** [docs/20260428_HERMES_VOICE_PLAN_V04.md](../20260428_HERMES_VOICE_PLAN_V04.md)

The Plan V04 itself looks healthy: the V03 issues (HTTPS-before-mic, audio-metadata frame, TTS chunking, cancellation, login protection, log/secret hygiene, conversation lifecycle) are all resolved. The TODO faithfully tracks the plan. What follows are the items I'd add or sharpen before starting implementation. None are fatal. Several would save real time during build-out.

---

## Recommended additions

### 1. Decide static-asset serving location once, in Phase 5 or 6

Phase 6 says "Serve the built web client through FastAPI **or** Nginx." Pick one and commit, because it changes Phase 5 work. Two reasonable options:

- **FastAPI `StaticFiles`** mounted at `/`. Simpler in dev (one origin, cookies and WS share scope), one process to operate.
- **Nginx serves `/`, proxies `/api` and `/ws` to FastAPI.** Slightly faster for assets, more moving parts.

For a single-host validation harness, FastAPI-serves-static is the lower-friction choice. Recommend stating that explicitly and removing the "or."

### 2. Add a Vite dev-server story

Vite defaults to `localhost:5173`; FastAPI will be on `localhost:8700`. Different origins means session cookies and WebSocket auth will not "just work" in dev. Add to Phase 5:

- Configure Vite `server.proxy` to forward `/api/*` and `/ws/*` to `127.0.0.1:8700`, **or**
- Build to `web/dist/` and have FastAPI serve it during dev too (slower iteration but no CORS).

This is a frequent multi-hour stumble; decide before Phase 5 starts.

### 3. Bound the inbound audio buffer per turn

Phase 4 says "buffer audio until `end_of_utterance`." Add an explicit cap (e.g., `MAX_UTTERANCE_BYTES`, default ~10 MB, configurable). Reject the turn with a standardized error if exceeded. Without this, a buggy or hostile client can OOM the backend.

### 4. Add TLS prerequisites to Phase 6

Phase 6 lists "Add Nginx TLS reverse proxy" but assumes the prerequisites exist. Explicit sub-items:

- Domain or subdomain pointing at the server (A/AAAA record).
- Ports 80 and 443 open on the host firewall and any upstream router.
- Certbot (or equivalent) installed and run; renewal hook in place.
- Nginx config for the chosen hostname tested with `nginx -t`.

These are the steps most likely to block a deploy day.

### 5. Reword the TTS line in Phase 3

Phase 3 says: "Implement `tts.py` for **streaming** OpenAI TTS output with `TTS_FORMAT=opus`." OpenAI's TTS API returns one blob per request; perceived streaming comes from the pipeline's chunking loop, not the TTS service. Suggest:

> "Implement `tts.py` as a non-streaming TTS request wrapper. Perceived streaming is achieved by the pipeline coordinator issuing one TTS request per text chunk; the TTS service itself returns complete audio per chunk."

This avoids future confusion when someone goes looking for SSE in `tts.py`.

### 6. Define session expiration in Phase 1

Phase 7 tests "session expiration" but no phase defines the policy. Add to Phase 1:

- Cookie `Max-Age` (e.g., 7 days for a personal tool, shorter if multi-user).
- Backend behavior on expired-cookie WS connect: close with a standardized error frame, not a silent disconnect.

### 7. Add a `/health` contract

Phase 1 says "add health route" but doesn't say what it returns. Recommend two endpoints:

- `/health/live` — process is up. No dependencies. Cheap. For systemd/uptime monitors.
- `/health/ready` — checks Hermes reachable on loopback and OpenAI key present. Slightly more expensive, suitable for human use.

### 8. Add a cancellation race-condition test in Phase 3

Phase 3 lists "tests for pipeline chunking, turn completion, and error propagation." Add specifically:

- A test that cancels a turn mid-TTS-write and asserts no further audio bytes are produced.
- A test that fires `new_session` while a Hermes SSE stream is open and asserts the prior task's `output_text.delta` events are dropped.

These are the bugs that look fine in unit tests and embarrass you in real use.

### 9. Note dev-time `.env` requirements

Phase 5 wires login to `HERMES_VOICE_WEB_PASSWORD`. Add a sub-item: "Create a development `api/.env` from `.env.example` with a known web password before Phase 5 testing." Obvious, but easy to forget when context-switching.

### 10. Hermes API key sourcing

`HERMES_API_KEY=<value of API_SERVER_KEY in ~/.hermes/.env>` is mentioned in the plan but not in the TODO. Add a Phase 0 or Phase 2 sub-item: "Read `API_SERVER_KEY` from `~/.hermes/.env` and place it in `api/.env` as `HERMES_API_KEY`." Otherwise the first Hermes smoke test fails with a 401 and the cause is non-obvious.

### 11. OpenAI cost guardrail (small but worth noting)

Whisper + TTS calls during iterative development can add up, especially with chatty test sessions. Add to Phase 9 (or earlier): "Track approximate per-turn STT/TTS cost during web validation and decide if a daily/weekly quota or alarm is warranted."

### 12. Phase 8 Flutter package shortlist

Phase 8 says "Add packages for audio capture, playback, WebSocket, audio session." Naming the leading candidates now saves judgment later. Suggest:

- Audio capture: `record`.
- Playback: `just_audio` (with Opus support).
- WebSocket: `web_socket_channel`.
- Audio session: `audio_session`.

Allowed to revise on the Mac, but having a starting set keeps Phase 8 from forking on package research.

---

## Smaller notes

- Phase 4 "Enforce V1 interrupt policy `ignore`: disable or drop inbound audio while a turn is active" — make sure the JSON control frame path is **never** dropped, only binary audio. `new_session` must be readable mid-turn or cancellation breaks.
- Phase 6 "Serve the built web client through FastAPI or Nginx" — see #1.
- Phase 7 latency "observations" — define target numbers (e.g., first-audio < 2.5s after end-of-utterance) so the observation has a pass/fail.
- Phase 0 smoke checks reference `scripts/smoke_responses_stream.py` and `scripts/smoke_whisper.py`. Confirm those exist or add a sub-item to create them before Phase 0 can be checked off.
- Add an explicit "rotate `SESSION_SECRET` and web password on first deploy" sub-item to Phase 6, since the example values must not survive into production.

---

## Overall

The TODO is in good shape and matches the plan. The most valuable changes are #1 (commit to a static-serving location), #2 (Vite dev-server proxy), #3 (max buffer cap), and #4 (TLS prerequisites). The rest are sharpening, not corrections. With those folded in, this TODO should carry the build cleanly through Phase 7 without surprise rework.
