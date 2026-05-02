# Local API backend agent instructions for mobile parallel work

Date: 2026-05-01

## 1. Purpose

These instructions are for an agent working on the HermesVoice FastAPI backend locally while a second agent works on the native iOS mobile app.

The goal is to make the local backend useful for mobile development and protocol testing on this Mac, even though there is no local Hermes agent instance on this computer.

This local backend work is a development aid. It does not replace final mobile acceptance against the public backend:

- `https://hermes-voice.dashanddata.com`
- `wss://hermes-voice.dashanddata.com/ws/voice`

## 2. Current project context

1. Repository:
   - `/Users/nick/Documents/HermesVoice`

2. Branch:
   - `dev_04_new_mobile`

3. Backend code:
   - `/Users/nick/Documents/HermesVoice/api`

4. Mobile planning TODO:
   - `/Users/nick/Documents/HermesVoice/docs/requirements/20260430_TODO_HERMES_VOICE_MOBILE_OS_INTEGRATION.md`

5. Public backend instructions:
   - `/Users/nick/Documents/HermesVoice/docs/20260430 Mobile App Public Backend Agent Instructions.md`

6. WebSocket protocol:
   - `/Users/nick/Documents/HermesVoice/docs/PROTOCOL.md`

7. iOS VAD spike result:
   - `/Users/nick/Documents/HermesVoice/docs/20260430_sherpa_onnx_vad_spike.md`
   - `/Users/nick/Documents/HermesVoice/docs/audio_spike/20260430_sherpa_onnx_vad_spike.md`

The sherpa-onnx VAD spike was a partial pass that is strong enough to proceed with built-in iPhone microphone VAD planning. Bluetooth headset microphone routing and a formal 5-minute stability run remain caveats.

## 3. Parallel work model

It is reasonable to run two agents concurrently:

1. Backend agent:
   - Owns local FastAPI setup, backend tests, local mock mode, protocol contract fixes, and documentation needed for the mobile agent.

2. Mobile agent:
   - Owns `mobile/ios/...`, Swift/SwiftUI app scaffold, vendored sherpa-onnx VAD, auth UI, WebSocket client, audio uplink, and audio downlink.

Coordinate through documented contracts rather than editing the same files. The backend agent should avoid changing `mobile/`. The mobile agent should avoid changing `api/` unless explicitly asked.

## 4. Important constraints

1. There is no local Hermes instance on this Mac.
2. Do not require `Hermes` to be running on `127.0.0.1:8642` for local mobile development.
3. Do not embed production credentials, API keys, bearer tokens, `.env` files, or personal secrets in source.
4. Do not change the public-backend default expected by the mobile plan.
5. Do not treat local backend success as final acceptance for the mobile app.
6. Keep the public origin as the real target for final testing.
7. If you add a mock or dev-only mode, make it explicit and guarded by environment variables.

## 5. Immediate backend questions to answer

1. Can a fresh local API environment start on this Mac using only placeholder development secrets?
2. Can the auth endpoints work locally with deterministic test credentials?
3. Can `/ws/voice` accept a developer bearer and return `session_started` after `client_hello`?
4. Can local `/ws/voice` run without a local Hermes process by using mock STT, mock Hermes text, and mock TTS bytes?
5. Does local protocol behavior match `docs/PROTOCOL.md` and the mobile TODO?
6. Can the mobile app test against local API only when explicitly configured to do so?

## 6. Known issues to check first

Run the mobile protocol tests first:

```bash
cd /Users/nick/Documents/HermesVoice/api
python3 -m pytest tests/test_mobile_v06_protocol.py -q
```

Previously observed failures:

1. `wav_pcm16` fallback sample-rate mismatch:
   - Test expects `downlink_sample_rate == 16000`.
   - `api/app/routes/voice.py` advertises `wav_pcm16` as `24000`.
   - Decide whether docs/tests or backend code should win. The mobile TODO currently says mandatory fallback is `wav_pcm16`, and older tests expect 16 kHz.

2. Stale test fake TTS signature:
   - Test helper `_fake_tts(text)` fails because production code calls `synthesize(chunk, format=tts_fmt)`.
   - Update tests or helper signatures as appropriate.

These are backend-contract hygiene issues and should be resolved before the mobile app relies on local protocol tests.

## 7. Suggested local setup

Create a local Python environment for development. Keep it inside or outside the repo according to the user's preference, but do not commit it.

Example:

```bash
cd /Users/nick/Documents/HermesVoice
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
```

Create a local `.env` only if needed:

```bash
cp api/.env.example api/.env
chmod 600 api/.env
```

Use placeholder values for local mock development. Do not use production secrets.

Minimum local values should include:

```bash
NAME_APP=hermes_voice_api_local
RUN_ENVIRONMENT=development
HERMES_VOICE_WEB_PASSWORD=test-password
HERMES_VOICE_WEB_EMAILS=allowed@example.com
HERMES_VOICE_API_KEY=test-api-key
SESSION_SECRET=test-session-secret-at-least-32-chars-long
OPENAI_API_KEY=sk-test-placeholder
HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=test
HERMES_MODEL=hermes-agent
```

The backend agent should consider adding explicit mock-mode variables rather than relying on fake keys accidentally failing:

```bash
HERMES_VOICE_MOCK_PIPELINE=1
HERMES_VOICE_MOCK_EMAIL=1
```

Only add these if implemented in code and documented.

## 8. Local server command

Start the API from the `api/` directory:

```bash
cd /Users/nick/Documents/HermesVoice/api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8700
```

Local API base URL:

- `http://127.0.0.1:8700`

Local WebSocket URL:

- `ws://127.0.0.1:8700/ws/voice`

Remember that this local URL is only for dev/testing. The mobile app default must remain the public HTTPS/WSS origin.

## 9. Desired local mock behavior

Because Hermes is not available locally, the backend should offer a clear dev-only way to exercise the mobile WebSocket pipeline.

Mock mode should ideally:

1. Accept `start_utterance`, binary audio frames, and `end_of_utterance`.
2. Avoid calling OpenAI Whisper for STT.
3. Avoid calling local Hermes `/responses`.
4. Avoid calling OpenAI TTS.
5. Return deterministic frames:
   - `transcript`
   - `active_state=thinking`
   - `turn_started`
   - `assistant_text`
   - `audio_chunk` prelude
   - binary audio bytes
   - `turn_completed`
   - `active_state=idle`
   - `turn_end`
6. Preserve all turn-id and stale-audio rules.
7. Preserve downlink negotiation:
   - `aac_adts`
   - `wav_pcm16`
   - `opus_ogg` for legacy web behavior if applicable
8. Make it obvious in logs that mock mode is enabled.

If realistic audio downlink is hard locally, prioritize protocol correctness first. For mobile audio playback work, produce a short valid `wav_pcm16` buffer when `wav_pcm16` is negotiated. For `aac_adts`, either generate valid AAC ADTS bytes or document that local AAC playback must be tested against the public backend.

## 10. Auth behavior for local mobile testing

The mobile app needs both cookie-based auth and developer-bearer WebSocket testing.

Backend agent should verify:

1. `GET /api/auth/session`
   - returns unauthenticated shape without crashing

2. `POST /api/auth/login`
   - accepts local test credentials from `.env`
   - does not send real email when mock email mode is enabled
   - returns `challenge_id`

3. `POST /api/auth/verify`
   - can complete in local mock/dev mode
   - sets `hv_session`

4. `POST /api/auth/logout`
   - clears `hv_session`

5. `/ws/voice`
   - accepts the `hv_session` cookie
   - accepts developer bearer only for local/dev testing
   - rejects unauthenticated callers with typed `AUTH_FAILED`

If adding a local email mock, do not print or store personal emails unnecessarily. Test credentials should use `allowed@example.com`.

## 11. Contract checks for mobile agent

Provide the mobile agent with exact local examples after backend setup.

Example unauthenticated session check:

```bash
curl -i http://127.0.0.1:8700/api/auth/session
```

Example login:

```bash
curl -i -X POST http://127.0.0.1:8700/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"email":"allowed@example.com","password":"test-password"}'
```

Example unauthenticated WebSocket result should be:

```json
{
  "event": "error",
  "error": {
    "code": "AUTH_FAILED",
    "message": "Authentication required",
    "status": 401
  }
}
```

Example `client_hello` payload:

```json
{
  "event": "client_hello",
  "client": "ios",
  "client_version": "0.0.1-dev",
  "accepted_downlink_formats": ["aac_adts", "wav_pcm16"]
}
```

Expected successful response:

```json
{
  "event": "session_started",
  "conversation_id": "<uuid>",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1
}
```

Also test fallback by sending:

```json
{
  "event": "client_hello",
  "client": "ios",
  "client_version": "0.0.1-dev",
  "accepted_downlink_formats": ["wav_pcm16"]
}
```

Record the exact returned `downlink_sample_rate` and align it with docs/tests.

## 12. Tests to run

Start with narrow backend tests:

```bash
cd /Users/nick/Documents/HermesVoice/api
python3 -m pytest tests/test_mobile_auth.py -q
python3 -m pytest tests/test_mobile_v06_protocol.py -q
```

Then run broader tests if the narrow ones pass:

```bash
python3 -m pytest -q
```

If provider-backed tests require real OpenAI or Hermes, mark the limitation and keep mock-mode contract tests green.

## 13. Files the backend agent is likely to touch

Likely backend files:

1. `api/app/config.py`
2. `api/app/routes/mobile_auth.py`
3. `api/app/routes/voice.py`
4. `api/app/services/pipeline.py`
5. `api/tests/test_mobile_auth.py`
6. `api/tests/test_mobile_v06_protocol.py`
7. New tests under `api/tests/`
8. Documentation under `docs/`

Avoid touching:

1. `mobile/`
2. sherpa-onnx fork files
3. web UI files unless needed for backend compatibility

## 14. Handoff back to the main HermesVoice agent

When finished, report:

1. Whether local API starts successfully.
2. Exact local base URL and WebSocket URL used.
3. Whether mock mode was implemented.
4. How mock mode is enabled.
5. Files changed.
6. Tests run and results.
7. Current `client_hello` negotiation behavior.
8. Current `wav_pcm16` sample-rate decision.
9. Auth routes verified locally.
10. Whether `/ws/voice` works with developer bearer.
11. Whether `/ws/voice` works with `hv_session` cookie.
12. Any remaining blockers for the mobile agent.
13. Any behavior that still must be verified against the public backend.

## 15. Summary

Parallel backend and mobile work is appropriate now that the sherpa-onnx physical iPhone VAD spike has substantially de-risked the mobile foundation. The backend agent should make the local API a trustworthy protocol and mock-pipeline target for the mobile agent, while preserving the project rule that final integration must still be tested against the public HermesVoice backend.
