# HermesVoice TODO

**Date:** 2026-04-28
**Scope:** Full monorepo V1 build
**Source plan:** `docs/20260427_HERMES_VOICE_PLAN_V02.md`

This is a single comprehensive TODO for the initial monorepo build. Split into
separate backend, mobile, and deployment TODO files only after those subprojects
exist and can advance independently.

## Phase 0 - Repository and Environment Baseline

- [ ] Initialize git repository if this workspace is intended to be source-controlled here.
- [ ] Add repo-level `.gitignore` covering Python caches, Flutter build output, local `.env` files, logs, and temporary audio artifacts.
- [ ] Keep the current root `venv/` treated as temporary development state, not production structure.
- [ ] Create the production Python venv at `/home/limited_user/environments/hermes_voice`.
- [ ] Verify the active Python command with `which python` and `python --version` before Python work.
- [ ] Add root README with project purpose, host assumptions, local setup, and smoke-test commands.
- [ ] Keep Hermes API server loopback-only at `127.0.0.1:8642`.
- [ ] Run smoke checks:
  - [ ] `python scripts/smoke_responses_stream.py`
  - [ ] `python scripts/smoke_whisper.py --generate both`
- [ ] Commit phase completion with a message referencing this TODO and Phase 0.

## Phase 1 - Backend Foundation

- [ ] Create `api/` FastAPI project structure from the V02 plan.
- [ ] Add backend dependency files for FastAPI, OpenAI SDK, pydantic-settings, httpx, pytest, uvicorn, and loguru.
- [ ] Add `api/.env.example` with `HERMES_VOICE_API_KEY`, `OPENAI_API_KEY`, `HERMES_BASE_URL`, `HERMES_API_KEY`, `HERMES_MODEL`, `STT_MODEL`, `TTS_MODEL`, `TTS_VOICE`, `TTS_FORMAT`, `UPLINK_FORMAT`, `DOWNLINK_FORMAT`, `RUN_ENVIRONMENT`, `NAME_APP`, and `PATH_TO_LOGS`.
- [ ] Implement `api/app/config.py` with validated settings and explicit fail-fast behavior for missing required variables.
- [ ] Implement centralized Loguru setup following `docs/LOGGING_PYTHON_V06.md`.
- [ ] Install uncaught exception logging via `sys.excepthook`, preserving `KeyboardInterrupt`.
- [ ] Implement standard API error responses following `docs/ERROR_REQUIREMENTS.md`.
- [ ] Add API-key auth middleware for phone-to-backend access.
- [ ] Add FastAPI app entrypoint and health route.
- [ ] Add pytest coverage for config validation, health route, auth failures, and standard error response shape.
- [ ] Run backend tests.
- [ ] Commit phase completion with a message referencing this TODO and Phase 1.

## Phase 2 - Hermes Responses Client

- [ ] Implement `api/app/services/hermes.py` using the OpenAI SDK against `HERMES_BASE_URL`.
- [ ] Use `responses.create(..., conversation=conversation_id, stream=True)`.
- [ ] Filter speakable output to `response.output_text.delta`.
- [ ] Ignore non-speakable Hermes events in V1 while preserving an internal place to classify tool progress later.
- [ ] Set long Hermes request timeout support, defaulting to 600 seconds.
- [ ] Add `scripts/smoke_hermes.sh` or update the existing Python smoke script documentation as the canonical Hermes connectivity check.
- [ ] Add pytest coverage for event filtering with representative streamed event objects.
- [ ] Run backend tests and Hermes smoke test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 2.

## Phase 3 - Audio Services and Headless Pipeline

- [ ] Implement `api/app/services/stt.py` for Whisper transcription of buffered audio bytes.
- [ ] Keep V1 uplink format as 16 kHz, 16-bit, mono WAV.
- [ ] Document `OGG(Opus)` as the later compressed uplink option, based on the smoke test results.
- [ ] Implement `api/app/services/tts.py` for streaming OpenAI TTS output with `TTS_FORMAT=opus`.
- [ ] Implement `api/app/services/pipeline.py` for STT to Hermes to TTS coordination.
- [ ] Batch Hermes text deltas into TTS-friendly chunks by sentence boundary or bounded buffer size.
- [ ] Structure pipeline turns as cancellable `asyncio.Task` instances for future interrupt policies.
- [ ] Add `scripts/smoke_pipeline.py` for text-in to audio-file-out validation without WebSocket.
- [ ] Add tests for STT/TTS service boundaries using mocks.
- [ ] Add tests for pipeline chunking, turn completion, and error propagation.
- [ ] Run backend tests and `scripts/smoke_pipeline.py`.
- [ ] Commit phase completion with a message referencing this TODO and Phase 3.

## Phase 4 - Backend WebSocket Voice Endpoint

- [ ] Implement `WS /ws/voice?api_key=...`.
- [ ] Mint one `conversation_id` per WebSocket session.
- [ ] Accept binary audio frames and buffer them until `{"event":"end_of_utterance"}`.
- [ ] Support `{"event":"new_session"}` by minting a new conversation id and clearing buffered audio.
- [ ] Emit JSON status frames for transcript, turn end, and standardized errors.
- [ ] Stream binary TTS audio frames back to the client as they arrive.
- [ ] Enforce V1 interrupt policy `ignore`: disable or drop inbound audio while a turn is active.
- [ ] Add idle timeout handling with default 120 seconds.
- [ ] Add rate limiting or connection guardrails appropriate for the LAN deployment.
- [ ] Add WebSocket tests for auth, buffering, end-of-utterance, new-session, turn-end, and error cases.
- [ ] Run backend tests and a local WebSocket smoke test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 4.

## Phase 5 - Flutter Mobile App Foundation

- [ ] Create `mobile/` Flutter project.
- [ ] Add packages for audio capture, playback, WebSocket transport, and audio session handling.
- [ ] Implement environment/config handling for backend WebSocket URL, API key, and V1 audio format.
- [ ] Implement WebSocket service that handles binary audio, binary playback bytes, and JSON status frames.
- [ ] Implement audio capture service for push-to-talk WAV uplink.
- [ ] Implement audio playback service for Opus downlink.
- [ ] Build primary conversation screen with push-to-talk control, connection state, talking state, and transcript display.
- [ ] Ensure unknown JSON event frames are ignored safely.
- [ ] Run Flutter analyzer and tests.
- [ ] Commit phase completion with a message referencing this TODO and Phase 5.

## Phase 6 - End-to-End LAN Validation

- [ ] Run backend locally on `avatar08` against Hermes loopback API.
- [ ] Connect physical iPhone to backend over the FSDC LAN.
- [ ] Verify push-to-talk capture, end-of-utterance, Whisper transcript, Hermes response streaming, TTS playback, and turn-end rearming.
- [ ] Capture latency observations for STT, Hermes first token, first audio playback, and full turn completion.
- [ ] Test a tool-using Hermes turn and confirm only text deltas are spoken.
- [ ] Test reconnect behavior after app backgrounding or transient network loss.
- [ ] Record any user attempts to interrupt turns for the future interrupt-policy decision.
- [ ] Commit phase completion with a message referencing this TODO and Phase 6.

## Phase 7 - Deployment Hardening

- [ ] Add production systemd unit for HermesVoice backend using `/home/limited_user/environments/hermes_voice`.
- [ ] Decide final deployment path for application code and align systemd `WorkingDirectory`.
- [ ] Configure `RUN_ENVIRONMENT=production`, `NAME_APP=hermes_voice_api`, and `PATH_TO_LOGS`.
- [ ] Verify production logs are file-only, rotated, retained, process-safe, and flushed on early exit.
- [ ] Add Nginx TLS reverse proxy only if phone access is needed outside the LAN.
- [ ] Confirm Hermes API server remains unexposed on loopback.
- [ ] Add operational README notes for restart, log inspection, smoke tests, and rollback.
- [ ] Run production smoke checks after systemd deployment.
- [ ] Commit phase completion with a message referencing this TODO and Phase 7.

## Phase 8 - V1 Polish and Reassessment

- [ ] Configure iOS audio session for playback with screen locked.
- [ ] Add reconnect and backoff behavior in the Flutter app.
- [ ] Review whether PTT should remain V1 interaction or whether VAD is justified.
- [ ] Review whether WAV uplink bandwidth matters enough to switch to `OGG(Opus)`.
- [ ] Review whether tool-progress JSON frames improve the experience.
- [ ] Review whether barge-in should stay ignored or move to cancel current turn.
- [ ] Add final V1 docs covering architecture, configuration, local development, deployment, and known tradeoffs.
- [ ] Run full backend tests, Flutter analyzer/tests, Hermes smoke, Whisper smoke, and end-to-end LAN test.
- [ ] Commit phase completion with a message referencing this TODO and Phase 8.
