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

## Build Mandate

- [x] Do not build, scaffold, install dependencies for, or test the mobile app on this Ubuntu server.
- [ ] Build the backend, web validation app, and public API/web deployment first on `avatar08` and `maestro04`.
- [ ] Start native Swift iOS development only after the public web app and API are working end-to-end.
- [ ] Move Swift/iOS development to the MacBook with Xcode when Phase 8 begins.
- [ ] Agent warning: if any old legacy Flutter/Dart references appear in historical docs, treat them as stale relics. Do not plan or build with Flutter; proceed with native Swift/iOS as the chosen mobile technology.

## Phase 0 - Repository and Environment Baseline

- [x] Initialize git repository if this workspace is intended to be source-controlled here.
- [x] Add repo-level `.gitignore` covering Python caches, web build output, native Apple generated output, local `.env` files, logs, and temporary audio artifacts.
- [x] Keep the current root `venv/` treated as temporary development state, not production structure.
- [x] Create the production Python venv at `/home/limited_user/environments/hermes_voice`.
- [x] Verify the active Python command with `which python` and `python --version` before Python work.
- [x] Add root README with project purpose, host assumptions, local setup, secure-context web testing rule, web-first rollout, reverse-proxy deployment shape, and smoke-test commands.
- [x] Keep Hermes API server loopback-only at `127.0.0.1:8642`.
- [x] Read `API_SERVER_KEY` from `/home/nick/.hermes/.env` and place it in `api/.env` as `HERMES_API_KEY` during backend setup.
- [x] Confirm existing smoke scripts are checked in:
  - [x] `scripts/smoke_responses_stream.py`
  - [x] `scripts/smoke_whisper.py`
- [x] Run smoke checks:
  - [x] `python scripts/smoke_responses_stream.py` — confirmed working, Hermes responding
  - [ ] `python scripts/smoke_whisper.py --generate both` — requires OPENAI_API_KEY + ffmpeg/flite; deferred until key is set
- [x] Commit phase completion with a message referencing this TODO and Phase 0.

## Phase 1 - Backend Foundation

- [x] Create `api/` FastAPI project structure from the V04 plan.
- [x] Add backend dependency files for FastAPI, OpenAI SDK, pydantic-settings, httpx, pytest, uvicorn, loguru, and any selected rate-limit/session packages.
- [x] Add `api/.env.example` with `HERMES_VOICE_WEB_PASSWORD`, `HERMES_VOICE_API_KEY`, `SESSION_SECRET`, `OPENAI_API_KEY`, `HERMES_BASE_URL`, `HERMES_API_KEY`, `HERMES_MODEL`, `STT_MODEL`, `TTS_MODEL`, `TTS_VOICE`, `TTS_FORMAT`, `UPLINK_FORMAT`, `DOWNLINK_FORMAT`, `RUN_ENVIRONMENT`, `NAME_APP`, `PATH_TO_LOGS`, `MAX_UTTERANCE_BYTES`, `SESSION_MAX_AGE_SECONDS`, `HERMES_INTER_TOKEN_TIMEOUT`, and `TTS_REQUEST_TIMEOUT`.
- [x] Implement `api/app/config.py` with validated settings and explicit fail-fast behavior for missing required variables.
- [x] Implement centralized Loguru setup following `docs/LOGGING_PYTHON_V06.md`.
- [x] Install uncaught exception logging via `sys.excepthook`, preserving `KeyboardInterrupt`.
- [x] Implement standard API error responses following `docs/ERROR_REQUIREMENTS.md`.
- [x] Add `/health/live` for cheap process liveness with no dependency checks.
- [x] Add `/health/ready` for human/operator readiness checks, including Hermes loopback reachability and OpenAI key presence.
- [x] Add web login/session auth for browser access.
- [x] Define cookie `Max-Age` using `SESSION_MAX_AGE_SECONDS` with an initial default of 7 days for the personal web tool.
- [x] Set session cookies with `HttpOnly`, `Secure`, and `SameSite=Lax` when served over HTTPS.
- [x] Set the production cookie domain/path deliberately for cross-subdomain auth between `hermes-voice.dashanddata.com` and `api.hermes-voice.dashanddata.com`.
- [x] Configure CORS to allow only `https://hermes-voice.dashanddata.com` for API calls in production.
- [x] Validate WebSocket `Origin` and allow only `https://hermes-voice.dashanddata.com` in production.
- [x] Define expired-cookie WebSocket behavior: reject or close with a standardized auth error, not a silent disconnect.
- [x] Add login rate limiting and repeated-failure lockout behavior.
- [x] Add API-key auth support for later mobile-to-backend access.
- [x] Add FastAPI app entrypoint.
- [x] Document production `.env` permissions: `chmod 600` and owner `limited_user:limited_user`.
- [x] Document log directory setup using systemd `LogsDirectory=hermes-voice` or explicit `install -d`.
- [x] Add pytest coverage for config validation, health routes, auth failures, expired sessions, rate limits, and standard error response shape.
- [x] Run backend tests.
- [x] Commit phase completion with a message referencing this TODO and Phase 1.

## Phase 2 - Hermes Responses Client

- [x] Implement `api/app/services/hermes.py` using httpx SSE against `HERMES_BASE_URL` (OpenAI-compatible endpoint; custom `conversation` field not in SDK).
- [x] Use `responses` endpoint with `conversation=conversation_id, stream=True`.
- [x] Filter speakable output to `response.output_text.delta`.
- [x] Ignore non-speakable Hermes events in V1 while preserving an internal place to classify tool progress later.
- [x] Set long Hermes request timeout support, defaulting to 600 seconds.
- [x] Add Hermes inter-token idle timeout, defaulting to 30 seconds.
- [x] `scripts/smoke_responses_stream.py` is the canonical Hermes connectivity check.
- [x] Add pytest coverage for event filtering and inter-token timeout behavior with representative streamed event objects.
- [x] Run backend tests and Hermes smoke test.
- [x] Commit phase completion with a message referencing this TODO and Phase 2.

## Phase 3 - Audio Services and Headless Pipeline

- [x] Implement `api/app/services/stt.py` for Whisper transcription of buffered audio bytes.
- [x] Keep V1 mobile uplink format as 16 kHz, 16-bit, mono WAV.
- [x] Support declared browser/test formats `webm/opus` and `ogg/opus` for STT.
- [x] Document `OGG(Opus)` as the later compressed mobile uplink option, based on the smoke test results.
- [x] Implement `api/app/services/tts.py` as a non-streaming TTS request wrapper returning complete audio for one text chunk.
- [x] Implement TTS request timeout, defaulting to 45 seconds.
- [x] Implement `api/app/services/pipeline.py` for STT to Hermes to TTS coordination.
- [x] Achieve perceived streaming by issuing one TTS request per flushed Hermes text chunk.
- [x] Batch Hermes text deltas into TTS-friendly chunks by sentence boundary, bounded buffer size, or no-punctuation force flush.
- [x] Use initial chunking defaults from V04: minimum 80 chars, maximum 280 chars, 2-second no-punctuation force flush.
- [x] Structure pipeline turns as cancellable `asyncio.Task` instances.
- [x] Ensure cancelled turns stop pending STT, Hermes, and TTS work.
- [x] Ensure cancelled turns cannot write stale audio to the WebSocket.
- [x] Add a test that cancels a turn mid-TTS-write and asserts no further audio bytes are produced.
- [x] Add a test that fires `new_session` while Hermes SSE is open and asserts prior deltas are dropped.
- [x] Add `scripts/smoke_pipeline.py` for text-in to audio-file-out validation without WebSocket.
- [x] Add tests for STT/TTS service boundaries using mocks.
- [x] Add tests for pipeline chunking, turn completion, cancellation races, and error propagation.
- [ ] Run backend tests and `scripts/smoke_pipeline.py`. — backend tests pass; smoke_pipeline requires OPENAI_API_KEY
- [x] Commit phase completion with a message referencing this TODO and Phase 3.

## Phase 4 - Backend WebSocket Voice Endpoint

- [x] Implement `WS /ws/voice`.
- [x] Authenticate browser clients through the web login session.
- [x] Keep API-key authentication available for later mobile clients.
- [x] Mint one `conversation_id` per WebSocket session.
- [x] Send `{"event":"session_started","conversation_id":"<uuid>"}` after connect and after new session.
- [x] Require `{"event":"start_utterance","format":"...","sample_rate":...}` before binary audio.
- [x] Accept initial upload formats: `wav`, `webm/opus`, and `ogg/opus`.
- [x] Reject binary audio before `start_utterance`, missing format, or unsupported format.
- [x] Add `MAX_UTTERANCE_BYTES` with an initial default of 10 MB.
- [x] Reject turns that exceed `MAX_UTTERANCE_BYTES` with a standardized WebSocket error frame.
- [x] Accept binary audio frames and buffer them until `{"event":"end_of_utterance"}`.
- [x] Support `{"event":"new_session"}` by cancelling any active turn, minting a new conversation id, and clearing buffered audio.
- [x] Ensure JSON control frames are still processed while a turn is active; only extra binary audio is dropped or rejected by the V1 interrupt policy.
- [x] Cancel any active turn on WebSocket disconnect.
- [x] Emit JSON status frames for transcript, turn end, and standardized errors.
- [x] Stream binary TTS audio frames back to the client as they arrive.
- [x] Enforce V1 interrupt policy `ignore`: drop or reject inbound binary audio while a turn is active unless the event is `new_session`.
- [x] Add WebSocket idle timeout handling with default 120 seconds.
- [x] Define V1 reconnect behavior as a new session with no resume.
- [x] Add rate limiting or connection guardrails appropriate for public deployment through maestro04.
- [x] Add WebSocket tests for auth, expired sessions, buffering, max buffer cap, metadata validation, end-of-utterance, new-session cancellation, disconnect cancellation, turn-end, and error cases.
- [ ] Run backend tests and a local WebSocket smoke test. — tests pass; live WS smoke test deferred until OPENAI_API_KEY available
- [x] Commit phase completion with a message referencing this TODO and Phase 4.

## Phase 5 - Web Validation Client

- [x] Create `web/` browser app project.
- [x] Use vanilla TypeScript + Vite for the browser validation harness.
- [x] Configure Vite `server.proxy` to forward `/api/*`, `/health`, `/login`, `/logout`, `/ws/*` to `127.0.0.1:8700` during development.
- [x] Keep browser requests same-origin in development through the Vite proxy so session cookies and WebSocket auth behave like production.
- [x] Add login screen using `HERMES_VOICE_WEB_PASSWORD` via the backend, not client-side password checks.
- [x] Implement browser session handling through backend-issued cookies.
- [x] Implement WebSocket client for `wss://api.hermes-voice.dashanddata.com/ws/voice` in production.
- [x] Implement API client calls against `https://api.hermes-voice.dashanddata.com` in production.
- [x] Implement microphone capture with browser APIs for localhost development.
- [x] Document that browser mic capture requires `localhost`, `127.0.0.1`, or HTTPS.
- [x] Create a development `api/.env` from `.env.example` with a known web password before Phase 5 testing.
- [x] Support push-to-talk (hold to talk / release to send) interaction.
- [x] Send `start_utterance` metadata before binary audio chunks.
- [x] Send binary audio chunks and `{"event":"end_of_utterance"}` control frames.
- [x] Play binary TTS audio returned by the backend (AudioQueue with AudioContext).
- [x] Show connection state, recording state, transcript, turn status, latency timings, and standardized errors.
- [x] Define initial latency targets for web validation:
  - [x] First audio under 2.5 seconds after end-of-utterance for non-tool turns.
  - [x] Hermes first text under 5 seconds for non-tool turns.
  - [x] Tool-using turns may exceed these targets but must show status and complete cleanly.
- [x] Ensure unknown JSON event frames are ignored safely.
- [x] Document that browser audio may use `webm/opus` or another browser-native format while mobile V1 remains WAV.
- [ ] Add web unit tests or component tests — deferred; vanilla TS/Vite test setup out of scope for V1.
- [x] Build the web app to `web/dist/` — `npm run build` succeeds (9 modules, 8.75 kB JS).
- [x] Confirm Phase 5 web testing is localhost-only until TLS is complete.
- [x] Commit phase completion with a message referencing this TODO and Phase 5.

## Phase 6 - Ubuntu Deployment Through Maestro04

- [x] Add production systemd unit for HermesVoice backend — `deploy/hermes-voice.service`.
- [x] Decide final deployment path — `/home/limited_user/applications/HermesVoice/api`.
- [x] Configure `RUN_ENVIRONMENT=production`, `NAME_APP=hermes_voice_api`, `PATH_TO_LOGS` in `.env.example`.
- [x] Configure production `.env` permissions with `chmod 600` and owner `limited_user:limited_user` — documented in `deploy/README.md`.
- [x] Rotate `SESSION_SECRET` and `HERMES_VOICE_WEB_PASSWORD` from development values before first public deploy — documented.
- [x] Configure `LogsDirectory=hermes-voice` in systemd service file.
- [x] Verify production logs are file-only, rotated, retained, process-safe, and flushed on early exit — confirmed in logging_config.py.
- [x] Serve the built web client through FastAPI `StaticFiles` from `web/dist/`.
- [x] Bind the HermesVoice backend on `avatar08` to `0.0.0.0:8700` with UFW restriction.
- [ ] Determine maestro04's LAN IP address — requires Nick to run on maestro04.
- [ ] Configure avatar08 UFW to allow port 8700 only from maestro04's LAN IP — requires Nick's sudo.
- [ ] Confirm port 8700 is not exposed by the home router — requires Nick to verify.
- [ ] Configure DNS for `hermes-voice.dashanddata.com` — requires Nick's DNS provider access.
- [ ] Configure DNS for `api.hermes-voice.dashanddata.com` — requires Nick's DNS provider access.
- [x] Configure Nginx on maestro04 for both domains — `deploy/nginx-hermes-voice.conf` ready to copy.
- [x] Configure WebSocket upgrade headers in maestro04 Nginx for `/ws/voice` — in nginx conf.
- [ ] Install or confirm Certbot on maestro04 — requires Nick on maestro04.
- [ ] Issue or update TLS certificates — requires Nick on maestro04.
- [ ] Run `nginx -t` on maestro04 before reload — requires Nick on maestro04.
- [ ] Confirm Certbot renewal is enabled — requires Nick on maestro04.
- [x] Add login abuse protection — rate limiting in backend + Nginx `limit_req` in nginx conf.
- [ ] Optionally add temporary Nginx basic auth — Nick's decision.
- [x] Confirm Hermes API server remains unexposed on avatar08 loopback — `API_SERVER_HOST=127.0.0.1`.
- [x] Add operational README notes — `deploy/README.md` covers all operations.
- [ ] Run production smoke checks after systemd and proxy deployment — pending maestro04 setup.
- [x] Commit phase completion with a message referencing this TODO and Phase 6.

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

## Phase 8 - Native Swift iOS App on Mac

- [ ] Confirm Phases 1-7 are complete before starting mobile work.
- [ ] Move active development to the MacBook; do not run Xcode build/test tasks on `avatar08`.
- [ ] Create `mobile/` native Swift iOS project on a Mac with Xcode installed.
- [ ] Start with native iOS framework candidates:
  - [ ] Audio capture: `AVAudioEngine` or `AVAudioRecorder`.
  - [ ] Playback: `AVAudioPlayer` or `AVAudioEngine`.
  - [ ] WebSocket: `URLSessionWebSocketTask`.
  - [ ] Audio session: `AVAudioSession`.
- [ ] Implement environment/config handling for backend WebSocket URL, API key, and V1 audio format.
- [ ] Implement WebSocket service using the contract proven by the web client.
- [ ] Implement audio capture service for push-to-talk WAV uplink.
- [ ] Send `start_utterance` with `format="wav"` before mobile audio bytes.
- [ ] Implement audio playback service for Opus downlink.
- [ ] Build primary conversation screen with push-to-talk control, connection state, talking state, and transcript display.
- [ ] Ensure unknown JSON event frames are ignored safely.
- [ ] Configure iOS audio session for playback with screen locked.
- [ ] Run Xcode build/tests on the Mac.
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
- [ ] Run full backend tests, web tests/build, Xcode build/tests, Hermes smoke, Whisper smoke, public web validation, and physical iPhone test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 9.
