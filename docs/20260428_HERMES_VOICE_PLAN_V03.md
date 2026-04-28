# HermesVoice - Project Plan V03

**Date:** 2026-04-28
**Supersedes:** `docs/20260427_HERMES_VOICE_PLAN_V02.md`
**Host of record:** `avatar08` (FSDC, Ubuntu)

HermesVoice is a real-time voice conversation layer for Hermes Agent. V03 keeps
the confirmed Hermes API architecture from V02, but changes the client rollout:
build and deploy a web test client on the Ubuntu server first, then build the
Flutter iOS app later on a Mac after the backend contract is proven.

---

## What changed since V02

- **Web client comes before Flutter.** The first UI is a browser-based test
  client served from this Ubuntu host, protected by a password from `.env`.
- **Flutter moves later.** The iOS app will be built and tested on a Mac. This
  Linux server will not have Xcode and will not run mobile build tooling.
- **Backend remains the source of truth.** The FastAPI backend, Hermes API
  integration, STT, TTS, logging, auth, and deployment all stay on Ubuntu.
- **Web app is a validation harness, not a second product.** It exists to prove
  the voice pipeline, WebSocket contract, auth, deployment, and public URL before
  mobile work starts.
- **V1 uplink remains WAV for mobile.** Whisper smoke tests showed WAV and
  `OGG(Opus)` both work. WAV remains the mobile V1 default because it is simpler
  and the latency was already acceptable. The web client may use browser-native
  audio formats such as `webm/opus` if needed.

---

## Architecture & Data Flow

### V1A - Web validation path

```
[Browser Web App]
    |
    |  1. Login with web password from .env
    |  2. Capture mic audio with MediaRecorder
    |  3. Send audio + control frames over WebSocket
    v
[FastAPI Backend - WS /ws/voice]
    |
    |  4. Buffer until end-of-utterance
    |  5. POST audio -> OpenAI Whisper -> transcript
    |  6. POST transcript -> Hermes /v1/responses
    |       conversation: "<session_id>"
    |  7. Receive text deltas via SSE
    |  8. Stream deltas -> OpenAI TTS
    |  9. Pipe TTS audio bytes back over WebSocket
    v
[Browser Web App]
    |
    | 10. Play returned audio and show transcript/status
```

### V1B - Mobile path after web validation

```
[Flutter App on iPhone]
    |
    |  1. Capture push-to-talk WAV audio
    |  2. Send binary audio + end-of-utterance over WebSocket
    v
[Same FastAPI Backend - Same /ws/voice contract]
    |
    |  3. Same STT -> Hermes -> TTS pipeline
    v
[Flutter App]
```

**Latency principle:** STT happens after end-of-utterance. Hermes and TTS are
pipelined: as soon as Hermes emits usable text deltas, the backend batches them
into TTS-friendly chunks and streams audio back to the client.

---

## Monorepo Structure

```
HermesVoice/
├── api/                              # FastAPI backend
│   ├── app/
│   │   ├── main.py                   # App entrypoint, routes, lifespan
│   │   ├── config.py                 # pydantic-settings from .env
│   │   ├── auth.py                   # API key and web session auth helpers
│   │   ├── errors.py                 # Standard API error responses
│   │   ├── logging_config.py         # Loguru setup
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── web.py                # Login + web app serving
│   │   │   └── voice.py              # WebSocket /ws/voice endpoint
│   │   └── services/
│   │       ├── stt.py                # OpenAI Whisper client
│   │       ├── hermes.py             # Hermes Responses API client
│   │       ├── tts.py                # OpenAI TTS client
│   │       └── pipeline.py           # STT -> Hermes -> TTS coordinator
│   ├── tests/
│   ├── .env.example
│   ├── requirements.txt
│   └── README.md
│
├── web/                              # Browser validation client
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── mobile/                           # Flutter iOS app, built later on Mac
│   └── README.md                     # Placeholder until mobile phase
│
├── scripts/
│   ├── smoke_responses_stream.py
│   ├── smoke_whisper.py
│   └── smoke_pipeline.py
│
├── docs/
├── .gitignore
└── README.md
```

---

## Backend - FastAPI (`api/`)

### Tech stack

| Concern | Library | Notes |
|---|---|---|
| Framework | FastAPI | Backend API and static web serving |
| WebSocket | FastAPI native | Browser/mobile to backend |
| STT | `openai` SDK -> Whisper | `whisper-1` initially |
| LLM | `openai` SDK -> Hermes | `base_url=http://127.0.0.1:8642/v1` |
| TTS | `openai` SDK -> TTS | Opus output for low-latency playback |
| Config | `pydantic-settings` | `.env` driven |
| Logging | Loguru | Follow `docs/LOGGING_PYTHON_V06.md` |
| HTTP client | `httpx` | Non-SDK HTTP calls if needed |
| Process manager | systemd | Ubuntu deployment |

### Production Python environment

The production virtual environment lives outside the repo:

```bash
/home/limited_user/environments/hermes_voice
```

Before Python work, verify the active interpreter:

```bash
which python
python --version
```

Do not use the root `venv/` as the production environment.

### Configuration (`api/.env.example`)

```env
# App identity and logging
NAME_APP=hermes_voice_api
RUN_ENVIRONMENT=development
PATH_TO_LOGS=/var/log/hermes-voice

# Browser login and backend API auth
HERMES_VOICE_WEB_PASSWORD=generate-strong-password
HERMES_VOICE_API_KEY=generate-with-openssl-rand-hex-32
SESSION_SECRET=generate-with-openssl-rand-hex-32

# OpenAI for STT + TTS
OPENAI_API_KEY=sk-...

# Hermes running locally on avatar08
HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<value of API_SERVER_KEY in ~/.hermes/.env>
HERMES_MODEL=hermes-agent

# Audio and timeouts
STT_MODEL=whisper-1
TTS_MODEL=tts-1
TTS_VOICE=alloy
TTS_FORMAT=opus
UPLINK_FORMAT=wav
DOWNLINK_FORMAT=opus
HERMES_REQUEST_TIMEOUT=600
IDLE_TIMEOUT=120
```

Missing required variables must fail fast at startup with clear fatal logs.

### Error responses

All HTTP errors follow `docs/ERROR_REQUIREMENTS.md`:

```json
{
  "error": {
    "code": "AUTH_FAILED",
    "message": "Authentication failed",
    "status": 401
  }
}
```

WebSocket errors use the same shape inside an outbound JSON frame:

```json
{
  "event": "error",
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Voice turn failed",
    "status": 500
  }
}
```

### Hermes client

Use the OpenAI SDK pointed at Hermes. Prefer the Responses API with
`conversation` so Hermes owns tool history and memory:

```python
stream = await client.responses.create(
    model=settings.HERMES_MODEL,
    input=text,
    conversation=conversation_id,
    stream=True,
)
```

Only `response.output_text.delta` is speakable in V1. Tool-progress events are
ignored by the speech path and can be surfaced as JSON status frames later.

### WebSocket endpoint

```
WS /ws/voice
```

- Browser clients authenticate through the web login session.
- Later mobile clients authenticate with `HERMES_VOICE_API_KEY`.
- Inbound frames are binary audio chunks plus JSON control frames.
- `{"event":"end_of_utterance"}` starts one voice turn.
- `{"event":"new_session"}` clears buffered audio and mints a new Hermes
  `conversation_id`.
- Outbound frames are binary TTS audio plus JSON status frames:
  `transcript`, `turn_end`, `error`, and later optional `tool_progress`.

---

## Web Client (`web/`)

The web client is the first deployed UI and primary end-to-end test harness.

### Required behavior

- Login form protected by `HERMES_VOICE_WEB_PASSWORD`.
- Browser session cookie after successful login.
- Push-to-talk or record/release control.
- WebSocket connection state.
- Microphone capture using browser APIs.
- Transcript display.
- Audio playback for backend TTS bytes.
- Turn state: idle, recording, transcribing, Hermes thinking, speaking, error.
- Latency timings for STT, Hermes first text, first audio, and full turn.
- Clear display of standardized backend errors.

### Audio format

Browsers may naturally produce `webm/opus` instead of WAV. The backend may accept
web formats for the browser harness while keeping `UPLINK_FORMAT=wav` as the
mobile V1 target. The web client's audio constraints must not force the mobile
format decision.

---

## Mobile App (`mobile/`) - Later Phase

The Flutter app is intentionally deferred until the backend and web harness are
proven on Ubuntu.

### Build environment

- Built on a Mac with Xcode.
- Tested on a physical iPhone.
- Uses the same backend URL and WebSocket contract proven by the web client.

### Expected V1 behavior

- Push-to-talk capture.
- 16 kHz, 16-bit, mono WAV uplink.
- Opus playback from backend TTS.
- Transcript and turn status display.
- Background audio handling through `audio_session`.

---

## Deployment

### Hermes

Hermes remains loopback-only:

```env
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
```

Do not expose the Hermes API server on LAN or the public internet. It has access
to Hermes tools, including terminal actions.

### HermesVoice backend and web app

The FastAPI service runs on Ubuntu and serves both API/WebSocket traffic and the
built web client.

```ini
[Unit]
Description=HermesVoice API
After=network.target

[Service]
User=limited_user
WorkingDirectory=/home/limited_user/applications/HermesVoice/api
EnvironmentFile=/home/limited_user/applications/HermesVoice/api/.env
ExecStart=/home/limited_user/environments/hermes_voice/bin/uvicorn app.main:app --host 127.0.0.1 --port 8700
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Nginx terminates TLS and proxies the public URL to `127.0.0.1:8700`, including
WebSocket upgrade headers. The backend should not listen publicly unless there
is a specific operational reason.

---

## Development Phases

### Phase 0 - Baseline and smoke tests

- Git repository, `.gitignore`, README, production venv path.
- Confirm Hermes Responses streaming smoke test.
- Confirm Whisper WAV and `OGG(Opus)` smoke tests.

### Phase 1 - Backend foundation

- FastAPI skeleton, settings, auth, errors, Loguru, health route, tests.

### Phase 2 - Hermes client

- Responses API streaming client, conversation id support, speakable event
  filtering, Hermes smoke test.

### Phase 3 - Audio services and headless pipeline

- Whisper STT, TTS streaming, pipeline coordinator, smoke pipeline script.

### Phase 4 - WebSocket voice endpoint

- `/ws/voice`, session conversation id, audio buffering, turn lifecycle,
  transcript/status/error frames, binary TTS streaming.

### Phase 5 - Web validation client

- Login, browser mic capture, record/release control, WebSocket client, playback,
  transcript/status view, latency timings.

### Phase 6 - Ubuntu deployment

- Production venv, systemd, Nginx TLS/public URL, logs, smoke checks.

### Phase 7 - End-to-end web validation

- Test the public web app from a browser, including tool-using Hermes turns and
  longer conversations.

### Phase 8 - Flutter iOS app on Mac

- Build the mobile app against the proven backend contract.

### Phase 9 - V1 reassessment

- Decide PTT vs VAD, WAV vs `OGG(Opus)`, tool-progress status frames, and
  interrupt policy based on real use.

---

## Current decisions

- **Hermes API:** local HTTP + SSE at `127.0.0.1:8642/v1`.
- **Conversation state:** owned by Hermes through `conversation`.
- **Backend state:** no transcript/history persistence in V1.
- **Initial deployed UI:** web client on Ubuntu.
- **Mobile app:** later, built on Mac.
- **Mobile V1 uplink:** WAV.
- **Compressed uplink option:** `OGG(Opus)`, not raw `.opus`.
- **Downlink:** Opus TTS audio.
- **Interrupt policy:** ignore during V1, but structure turns as cancellable tasks.
- **Auth:** web password for browser UI, API key for later mobile/backend access.

---

## Still open after web validation

- Whether the browser client should remain as an operational admin/test tool.
- Whether mobile uplink should stay WAV after real-world network tests.
- Whether VAD improves the experience compared with push-to-talk.
- Whether tool-progress JSON frames are useful or noisy.
- Whether barge-in is worth implementing.
