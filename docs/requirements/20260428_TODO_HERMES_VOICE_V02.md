# HermesVoice TODO V02

**Date:** 2026-04-28
**Scope:** Full monorepo V1 build
**Source plan:** `docs/20260428_HERMES_VOICE_PLAN_V04.md`
**Supersedes:** `docs/requirements/20260428_TODO_HERMES_VOICE.md`

This TODO carries forward the V04 plan and sharpens the implementation details
needed for a public web deployment through the FSDC reverse proxy architecture.
Public traffic enters through `maestro04` Nginx, then proxies to the backend on
`avatar08` (`192.168.0.244`). The public web app base URL is
`https://hermes-voice.dashanddata.com`; the backend API/WebSocket base URL is
`https://api.hermes-voice.dashanddata.com`. Hermes itself remains loopback-only
on `avatar08`.

## Phase 0 - Repository and Environment Baseline

- [ ] Initialize git repository if this workspace is intended to be source-controlled here.
- [ ] Add repo-level `.gitignore` covering Python caches, web build output, Flutter build output, local `.env` files, logs, and temporary audio artifacts.
- [ ] Keep the current root `venv/` treated as temporary development state, not production structure.
- [ ] Create the production Python venv at `/home/limited_user/environments/hermes_voice`.
- [ ] Verify the active Python command with `which python` and `python --version` before Python work.
- [ ] Add root README with project purpose, host assumptions, local setup, secure-context web testing rule, web-first rollout, reverse-proxy deployment shape, and smoke-test commands.
- [ ] Keep Hermes API server loopback-only at `127.0.0.1:8642`.
- [ ] Read `API_SERVER_KEY` from `/home/nick/.hermes/.env` and place it in `api/.env` as `HERMES_API_KEY` during backend setup.
- [ ] Confirm existing smoke scripts are checked in:
  - [ ] `scripts/smoke_responses_stream.py`
  - [ ] `scripts/smoke_whisper.py`
- [ ] Run smoke checks:
  - [ ] `python scripts/smoke_responses_stream.py`
  - [ ] `python scripts/smoke_whisper.py --generate both`
- [ ] Commit phase completion with a message referencing this TODO and Phase 0.

## Phase 1 - Backend Foundation

- [ ] Create `api/` FastAPI project structure from the V04 plan.
- [ ] Add backend dependency files for FastAPI, OpenAI SDK, pydantic-settings, httpx, pytest, uvicorn, loguru, and any selected rate-limit/session packages.
- [ ] Add `api/.env.example` with `HERMES_VOICE_WEB_PASSWORD`, `HERMES_VOICE_API_KEY`, `SESSION_SECRET`, `OPENAI_API_KEY`, `HERMES_BASE_URL`, `HERMES_API_KEY`, `HERMES_MODEL`, `STT_MODEL`, `TTS_MODEL`, `TTS_VOICE`, `TTS_FORMAT`, `UPLINK_FORMAT`, `DOWNLINK_FORMAT`, `RUN_ENVIRONMENT`, `NAME_APP`, `PATH_TO_LOGS`, `MAX_UTTERANCE_BYTES`, `SESSION_MAX_AGE_SECONDS`, `HERMES_INTER_TOKEN_TIMEOUT`, and `TTS_REQUEST_TIMEOUT`.
- [ ] Implement `api/app/config.py` with validated settings and explicit fail-fast behavior for missing required variables.
- [ ] Implement centralized Loguru setup following `docs/LOGGING_PYTHON_V06.md`.
- [ ] Install uncaught exception logging via `sys.excepthook`, preserving `KeyboardInterrupt`.
- [ ] Implement standard API error responses following `docs/ERROR_REQUIREMENTS.md`.
- [ ] Add `/health/live` for cheap process liveness with no dependency checks.
- [ ] Add `/health/ready` for human/operator readiness checks, including Hermes loopback reachability and OpenAI key presence.
- [ ] Add web login/session auth for browser access.
- [ ] Define cookie `Max-Age` using `SESSION_MAX_AGE_SECONDS` with an initial default of 7 days for the personal web tool.
- [ ] Set session cookies with `HttpOnly`, `Secure`, and `SameSite=Lax` when served over HTTPS.
- [ ] Set the production cookie domain/path deliberately for cross-subdomain auth between `hermes-voice.dashanddata.com` and `api.hermes-voice.dashanddata.com`.
- [ ] Configure CORS to allow only `https://hermes-voice.dashanddata.com` for API calls in production.
- [ ] Validate WebSocket `Origin` and allow only `https://hermes-voice.dashanddata.com` in production.
- [ ] Define expired-cookie WebSocket behavior: reject or close with a standardized auth error, not a silent disconnect.
- [ ] Add login rate limiting and repeated-failure lockout behavior.
- [ ] Add API-key auth support for later mobile-to-backend access.
- [ ] Add FastAPI app entrypoint.
- [ ] Document production `.env` permissions: `chmod 600` and owner `limited_user:limited_user`.
- [ ] Document log directory setup using systemd `LogsDirectory=hermes-voice` or explicit `install -d`.
- [ ] Add pytest coverage for config validation, health routes, auth failures, expired sessions, rate limits, and standard error response shape.
- [ ] Run backend tests.
- [ ] Commit phase completion with a message referencing this TODO and Phase 1.

## Phase 2 - Hermes Responses Client

- [ ] Implement `api/app/services/hermes.py` using the OpenAI SDK against `HERMES_BASE_URL`.
- [ ] Use `responses.create(..., conversation=conversation_id, stream=True)`.
- [ ] Filter speakable output to `response.output_text.delta`.
- [ ] Ignore non-speakable Hermes events in V1 while preserving an internal place to classify tool progress later.
- [ ] Set long Hermes request timeout support, defaulting to 600 seconds.
- [ ] Add Hermes inter-token idle timeout, defaulting to 30 seconds.
- [ ] Add `scripts/smoke_hermes.sh` or update the existing Python smoke script documentation as the canonical Hermes connectivity check.
- [ ] Add pytest coverage for event filtering and inter-token timeout behavior with representative streamed event objects.
- [ ] Run backend tests and Hermes smoke test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 2.

## Phase 3 - Audio Services and Headless Pipeline

- [ ] Implement `api/app/services/stt.py` for Whisper transcription of buffered audio bytes.
- [ ] Keep V1 mobile uplink format as 16 kHz, 16-bit, mono WAV.
- [ ] Support declared browser/test formats `webm/opus` and `ogg/opus` for STT.
- [ ] Document `OGG(Opus)` as the later compressed mobile uplink option, based on the smoke test results.
- [ ] Implement `api/app/services/tts.py` as a non-streaming TTS request wrapper returning complete audio for one text chunk.
- [ ] Implement TTS request timeout, defaulting to 45 seconds.
- [ ] Implement `api/app/services/pipeline.py` for STT to Hermes to TTS coordination.
- [ ] Achieve perceived streaming by issuing one TTS request per flushed Hermes text chunk.
- [ ] Batch Hermes text deltas into TTS-friendly chunks by sentence boundary, bounded buffer size, or no-punctuation force flush.
- [ ] Use initial chunking defaults from V04: minimum 80 chars, maximum 280 chars, 2-second no-punctuation force flush.
- [ ] Structure pipeline turns as cancellable `asyncio.Task` instances.
- [ ] Ensure cancelled turns stop pending STT, Hermes, and TTS work.
- [ ] Ensure cancelled turns cannot write stale audio to the WebSocket.
- [ ] Add a test that cancels a turn mid-TTS-write and asserts no further audio bytes are produced.
- [ ] Add a test that fires `new_session` while Hermes SSE is open and asserts prior deltas are dropped.
- [ ] Add `scripts/smoke_pipeline.py` for text-in to audio-file-out validation without WebSocket.
- [ ] Add tests for STT/TTS service boundaries using mocks.
- [ ] Add tests for pipeline chunking, turn completion, cancellation races, and error propagation.
- [ ] Run backend tests and `scripts/smoke_pipeline.py`.
- [ ] Commit phase completion with a message referencing this TODO and Phase 3.

## Phase 4 - Backend WebSocket Voice Endpoint

- [ ] Implement `WS /ws/voice`.
- [ ] Authenticate browser clients through the web login session.
- [ ] Keep API-key authentication available for later mobile clients.
- [ ] Mint one `conversation_id` per WebSocket session.
- [ ] Send `{"event":"session_started","conversation_id":"<uuid>"}` after connect and after new session.
- [ ] Require `{"event":"start_utterance","format":"...","sample_rate":...}` before binary audio.
- [ ] Accept initial upload formats: `wav`, `webm/opus`, and `ogg/opus`.
- [ ] Reject binary audio before `start_utterance`, missing format, or unsupported format.
- [ ] Add `MAX_UTTERANCE_BYTES` with an initial default of 10 MB.
- [ ] Reject turns that exceed `MAX_UTTERANCE_BYTES` with a standardized WebSocket error frame.
- [ ] Accept binary audio frames and buffer them until `{"event":"end_of_utterance"}`.
- [ ] Support `{"event":"new_session"}` by cancelling any active turn, minting a new conversation id, and clearing buffered audio.
- [ ] Ensure JSON control frames are still processed while a turn is active; only extra binary audio is dropped or rejected by the V1 interrupt policy.
- [ ] Cancel any active turn on WebSocket disconnect.
- [ ] Emit JSON status frames for transcript, turn end, and standardized errors.
- [ ] Stream binary TTS audio frames back to the client as they arrive.
- [ ] Enforce V1 interrupt policy `ignore`: drop or reject inbound binary audio while a turn is active unless the event is `new_session`.
- [ ] Add WebSocket idle timeout handling with default 120 seconds.
- [ ] Define V1 reconnect behavior as a new session with no resume.
- [ ] Add rate limiting or connection guardrails appropriate for public deployment through maestro04.
- [ ] Add WebSocket tests for auth, expired sessions, buffering, max buffer cap, metadata validation, end-of-utterance, new-session cancellation, disconnect cancellation, turn-end, and error cases.
- [ ] Run backend tests and a local WebSocket smoke test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 4.

## Phase 5 - Web Validation Client

- [ ] Create `web/` browser app project.
- [ ] Use vanilla TypeScript + Vite for the browser validation harness.
- [ ] Configure Vite `server.proxy` to forward `/api/*` and `/ws/*` to `127.0.0.1:8700` during development.
- [ ] Keep browser requests same-origin in development through the Vite proxy so session cookies and WebSocket auth behave like production.
- [ ] Add login screen using `HERMES_VOICE_WEB_PASSWORD` via the backend, not client-side password checks.
- [ ] Implement browser session handling through backend-issued cookies.
- [ ] Implement WebSocket client for `wss://api.hermes-voice.dashanddata.com/ws/voice` in production.
- [ ] Implement API client calls against `https://api.hermes-voice.dashanddata.com` in production.
- [ ] Implement microphone capture with browser APIs for localhost development.
- [ ] Document that browser mic capture requires `localhost`, `127.0.0.1`, or HTTPS.
- [ ] Create a development `api/.env` from `.env.example` with a known web password before Phase 5 testing.
- [ ] Support push-to-talk or record/release interaction.
- [ ] Send `start_utterance` metadata before binary audio chunks.
- [ ] Send binary audio chunks and `{"event":"end_of_utterance"}` control frames.
- [ ] Play binary TTS audio returned by the backend.
- [ ] Show connection state, recording state, transcript, turn status, latency timings, and standardized errors.
- [ ] Define initial latency targets for web validation:
  - [ ] First audio under 2.5 seconds after end-of-utterance for non-tool turns.
  - [ ] Hermes first text under 5 seconds for non-tool turns.
  - [ ] Tool-using turns may exceed these targets but must show status and complete cleanly.
- [ ] Ensure unknown JSON event frames are ignored safely.
- [ ] Document that browser audio may use `webm/opus` or another browser-native format while mobile V1 remains WAV.
- [ ] Add web unit tests or component tests for auth state, WebSocket status handling, metadata send, reconnect state, and error display.
- [ ] Build the web app to `web/dist/`.
- [ ] Confirm Phase 5 web testing is localhost-only until TLS is complete.
- [ ] Commit phase completion with a message referencing this TODO and Phase 5.

## Phase 6 - Ubuntu Deployment Through Maestro04

- [ ] Add production systemd unit for HermesVoice backend using `/home/limited_user/environments/hermes_voice`.
- [ ] Decide final deployment path for application code and align systemd `WorkingDirectory`.
- [ ] Configure `RUN_ENVIRONMENT=production`, `NAME_APP=hermes_voice_api`, and `PATH_TO_LOGS`.
- [ ] Configure production `.env` permissions with `chmod 600` and owner `limited_user:limited_user`.
- [ ] Rotate `SESSION_SECRET` and `HERMES_VOICE_WEB_PASSWORD` from development values before first public deploy.
- [ ] Configure `LogsDirectory=hermes-voice` in systemd or explicitly create and chown `/var/log/hermes-voice`.
- [ ] Verify production logs are file-only, rotated, retained, process-safe, and flushed on early exit.
- [ ] Serve the built web client through FastAPI `StaticFiles` from `web/dist/`.
- [ ] Bind the HermesVoice backend on `avatar08` to an address reachable by `maestro04` but not publicly exposed directly, such as `192.168.0.244:8700` or `0.0.0.0:8700` with firewall restrictions.
- [ ] Determine maestro04's LAN IP address.
- [ ] Configure avatar08 UFW to allow port 8700 only from maestro04's LAN IP.
- [ ] Confirm port 8700 is not exposed by the home router; public 80/443 stay routed only to maestro04.
- [ ] Configure DNS for `hermes-voice.dashanddata.com` to point to the public FSDC IP routed to maestro04.
- [ ] Configure DNS for `api.hermes-voice.dashanddata.com` to point to the public FSDC IP routed to maestro04.
- [ ] Configure Nginx on maestro04 for `hermes-voice.dashanddata.com` to serve or proxy the public web app.
- [ ] Configure Nginx on maestro04 for `api.hermes-voice.dashanddata.com` to proxy API and WebSocket traffic to `avatar08:8700`.
- [ ] Configure WebSocket upgrade headers in maestro04 Nginx for `/ws/voice`.
- [ ] Install or confirm Certbot on maestro04.
- [ ] Issue or update TLS certificates for `hermes-voice.dashanddata.com` and `api.hermes-voice.dashanddata.com`.
- [ ] Run `nginx -t` on maestro04 before reload.
- [ ] Confirm Certbot renewal is enabled and run `certbot renew --dry-run`.
- [ ] Add login abuse protection at backend or maestro04 Nginx before public exposure.
- [ ] Optionally add temporary Nginx basic auth or an unguessable path prefix while the web app remains private.
- [ ] Confirm Hermes API server remains unexposed on avatar08 loopback.
- [ ] Add operational README notes for maestro04 proxy config, avatar08 systemd restart, log inspection, smoke tests, and rollback.
- [ ] Run production smoke checks after systemd and proxy deployment.
- [ ] Commit phase completion with a message referencing this TODO and Phase 6.

## Phase 7 - Public End-to-End Web Validation

- [ ] Open the public web app URL from a browser outside the server.
- [ ] Confirm the public web app is served over HTTPS before testing microphone capture.
- [ ] Verify login with the production `.env` web password.
- [ ] Verify login rate limiting and session cookie flags.
- [ ] Verify microphone permission handling and recording.
- [ ] Verify `start_utterance` metadata handling, end-of-utterance handling, Whisper transcript, Hermes response streaming, TTS playback, and turn-end rearming.
- [ ] Capture latency observations for STT, Hermes first text, first audio playback, and full turn completion.
- [ ] Compare observed latency against Phase 5 targets and record misses.
- [ ] Test a tool-using Hermes turn and confirm only text deltas are spoken.
- [ ] Test reconnect behavior after tab refresh, network interruption, and session expiration.
- [ ] Confirm reconnect creates a new session in V1.
- [ ] Record browser audio format details and any backend transcoding needed.
- [ ] Track approximate per-turn Whisper and TTS cost during validation.
- [ ] Decide whether a daily/weekly OpenAI usage quota or billing alert is warranted.
- [ ] Commit phase completion with a message referencing this TODO and Phase 7.

## Phase 8 - Flutter Mobile App on Mac

- [ ] Create `mobile/` Flutter project on a Mac with Xcode installed.
- [ ] Start with package candidates:
  - [ ] Audio capture: `record`.
  - [ ] Playback: `just_audio`.
  - [ ] WebSocket: `web_socket_channel`.
  - [ ] Audio session: `audio_session`.
- [ ] Implement environment/config handling for backend WebSocket URL, API key, and V1 audio format.
- [ ] Implement WebSocket service using the contract proven by the web client.
- [ ] Implement audio capture service for push-to-talk WAV uplink.
- [ ] Send `start_utterance` with `format="wav"` before mobile audio bytes.
- [ ] Implement audio playback service for Opus downlink.
- [ ] Build primary conversation screen with push-to-talk control, connection state, talking state, and transcript display.
- [ ] Ensure unknown JSON event frames are ignored safely.
- [ ] Configure iOS audio session for playback with screen locked.
- [ ] Run Flutter analyzer and tests on the Mac.
- [ ] Test on a physical iPhone against the deployed Ubuntu backend.
- [ ] Commit phase completion with a message referencing this TODO and Phase 8.

## Phase 9 - V1 Polish and Reassessment

- [ ] Decide whether the web client should remain as an operational admin/test tool after mobile ships.
- [ ] Add reconnect and backoff behavior where needed in web and mobile clients.
- [ ] Review whether PTT should remain V1 interaction or whether VAD is justified.
- [ ] Review whether WAV uplink bandwidth matters enough to switch to `OGG(Opus)`.
- [ ] Review whether tool-progress JSON frames improve the experience.
- [ ] Review whether barge-in should stay ignored or move to cancel current turn.
- [ ] Re-evaluate `TTS_MODEL` against newer lower-latency TTS models using first-audio measurements.
- [ ] Add final V1 docs covering architecture, configuration, local development, maestro04 deployment, avatar08 service operations, and known tradeoffs.
- [ ] Run full backend tests, web tests/build, Flutter analyzer/tests, Hermes smoke, Whisper smoke, public web validation, and physical iPhone test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 9.
