# HermesVoice - Project Plan V04

**Date:** 2026-04-28
**Supersedes:** `docs/20260428_HERMES_VOICE_PLAN_V03.md`
**Host of record:** `avatar08` (FSDC, Ubuntu)

HermesVoice is a real-time voice conversation layer for Hermes Agent. V04 keeps
the web-first rollout from V03, but tightens the parts that can otherwise cause
implementation ambiguity: browser HTTPS requirements, WebSocket audio metadata,
TTS chunking, cancellation, login protection, deployment prerequisites, and
conversation lifecycle.

---

## What changed since V03

- **Secure-context rule is explicit.** Browser mic capture only works on
  `localhost`, `127.0.0.1`, or HTTPS. Phase 5 web testing is localhost-only
  until Phase 6 provisions the public HTTPS URL.
- **WebSocket audio metadata is required.** Every utterance starts with a
  `start_utterance` JSON frame that declares audio format and sample rate before
  binary audio arrives.
- **TTS streaming is defined as chunked requests.** The backend creates
  perceived streaming by chunking Hermes text and issuing TTS requests per chunk.
- **Cancellation is part of the WebSocket design.** Disconnects and
  `new_session` cancel in-flight turns and prevent old audio from being written.
- **Public login has minimum abuse protection.** Login rate limiting, secure
  cookies, and optional Nginx shielding are required before public exposure.
- **Deployment secrets and logs are specified.** `.env` permissions and log
  directory ownership are deployment tasks, not implicit assumptions.
- **Conversation and reconnect behavior is explicit.** V1 treats disconnect as
  a new session; no resume behavior is promised yet.

---

## Architecture & Data Flow

### V1A - Web validation path

```
[Browser Web App]
    |
    |  1. Login over HTTPS, or localhost during development
    |  2. Capture mic audio with MediaRecorder
    |  3. Send start_utterance metadata
    |  4. Send binary audio + end_of_utterance over WebSocket
    v
[FastAPI Backend - WS /ws/voice]
    |
    |  5. Validate metadata and buffer audio
    |  6. POST audio -> OpenAI Whisper -> transcript
    |  7. POST transcript -> Hermes /v1/responses
    |       conversation: "<conversation_id>"
    |  8. Receive text deltas via SSE
    |  9. Chunk text -> repeated OpenAI TTS requests
    | 10. Pipe TTS audio bytes back over WebSocket
    v
[Browser Web App]
    |
    | 11. Play returned audio and show transcript/status/timings
```

### V1B - Mobile path after web validation

```
[Native Swift iOS App on iPhone]
    |
    |  1. Capture push-to-talk WAV audio
    |  2. Send start_utterance metadata
    |  3. Send binary audio + end_of_utterance over WebSocket
    v
[Same FastAPI Backend - Same /ws/voice contract]
    |
    |  4. Same STT -> Hermes -> TTS pipeline
    v
[Native Swift iOS App]
```

**Latency principle:** STT starts after end-of-utterance. Hermes and TTS are
pipelined after transcription: the backend buffers Hermes text until it has a
useful TTS chunk, starts TTS for that chunk, and continues reading Hermes while
audio is being generated and sent.

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
├── mobile/
│   └── ios/
│       └── HermesVoice/              # Native Swift/SwiftUI iOS app project
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
| TTS | `openai` SDK -> TTS | Configurable; start with `tts-1` |
| Config | `pydantic-settings` | `.env` driven |
| Logging | Loguru | Follow `docs/LOGGING_PYTHON_V06.md` |
| HTTP client | `httpx` | Non-SDK HTTP calls if needed |
| Login protection | Backend limiter or Nginx `limit_req` | Required before public exposure |
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
HERMES_INTER_TOKEN_TIMEOUT=30
TTS_REQUEST_TIMEOUT=45
IDLE_TIMEOUT=120
```

Missing required variables must fail fast at startup with clear fatal logs.

### Secret hygiene

- `api/.env` is never committed.
- Production `.env` permissions: `chmod 600 api/.env`.
- Production `.env` owner: `limited_user:limited_user`.
- The file contains OpenAI keys, Hermes API key, session secret, and web
  password; do not print it in logs.

### Logging deployment prerequisite

Use one of these approaches before starting the production service:

- Prefer `systemd` `LogsDirectory=hermes-voice` so systemd creates
  `/var/log/hermes-voice` with service ownership.
- Or explicitly create and chown the directory before deploy:
  `sudo install -d -o limited_user -g limited_user /var/log/hermes-voice`.

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

---

## Hermes Client

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

Timeouts:

- Overall Hermes request timeout defaults to 600 seconds.
- Inter-token timeout defaults to 30 seconds; abort if the SSE stream is open
  but produces no event or text delta for that interval.
- Timeout errors become standardized WebSocket `error` frames.

---

## Voice Pipeline and TTS Chunking

OpenAI TTS returns audio per request. HermesVoice gets perceived streaming by
chunking Hermes text and making multiple TTS requests.

### Chunking heuristic

- Append each `response.output_text.delta` to a text buffer.
- Flush on sentence punctuation: `.`, `?`, `!`, or newline.
- Flush on clause punctuation after a minimum useful length: `,`, `;`, `:`.
- Force-flush if the buffer exceeds a configured character limit.
- Force-flush if no punctuation arrives for a configured time window.
- After Hermes completes, flush any remaining buffer.

Initial defaults:

- Minimum flush size: 80 characters.
- Maximum flush size: 280 characters.
- No-punctuation force flush: 2 seconds after first buffered text.

### TTS request behavior

- One TTS request per flushed chunk.
- TTS model is configurable through `TTS_MODEL`; start with `tts-1`.
- Re-evaluate lower-latency TTS models after the web harness can measure
  first-audio latency.
- TTS request timeout defaults to 45 seconds.
- Audio chunks are sent to the client in the order their text chunks were
  flushed.
- If a turn is cancelled, pending TTS work must stop and no further audio from
  that turn may be written to the WebSocket.

---

## WebSocket Contract

```
WS /ws/voice
```

Browser clients authenticate through the web login session. Later mobile clients
authenticate with `HERMES_VOICE_API_KEY`.

### Conversation lifecycle

- Backend mints a new `conversation_id` on WebSocket connect.
- Backend sends:

```json
{"event":"session_started","conversation_id":"<uuid>"}
```

- The same conversation id is reused for all turns on that socket.
- `{"event":"new_session"}` cancels any active turn, clears buffered audio,
  mints a new conversation id, and emits a new `session_started` frame.
- WebSocket disconnect cancels any active turn.
- V1 reconnect behavior: reconnect means a new session. No resume behavior is
  promised until a later phase.

### Required inbound sequence per utterance

Start every utterance with metadata:

```json
{
  "event": "start_utterance",
  "format": "webm/opus",
  "sample_rate": 48000
}
```

Then send binary audio frames. End the utterance with:

```json
{"event":"end_of_utterance"}
```

Accepted initial formats:

- `wav` for mobile V1 and debug fixtures.
- `webm/opus` for browser MediaRecorder where supported.
- `ogg/opus` for compressed test fixtures.

Reject turns that send binary audio before `start_utterance`, omit `format`, or
declare an unsupported format.

### Outbound frames

JSON status frames:

- `session_started`
- `transcript`
- `assistant_text`
- `active_state`
- `turn_started`
- `turn_completed`
- `turn_end`
- `voice_turn_skipped`
- `pong`
- `error`

Current `active_state` values are:

- `idle`
- `listening`
- `thinking`
- `thinking_progress`
- `speaking`
- `awaiting_approval`

Binary frames:

- TTS audio bytes for the active turn only.

Unknown future JSON frames must be safe for clients to ignore.

### Cancellation rules

- Store each voice turn as a per-session `asyncio.Task`.
- Cancel active turn on `new_session` or socket disconnect.
- Propagate cancellation through STT, Hermes SSE, and TTS calls.
- Guard every outbound audio write with the active turn id so cancelled turns
  cannot write stale audio.
- V1 interrupt policy remains `ignore`: audio received while a turn is active is
  dropped or rejected unless the event is `new_session`.

### Idle behavior

- `IDLE_TIMEOUT` gates no WebSocket traffic in either direction.
- Hermes inter-token timeout gates a stuck SSE stream.
- TTS request timeout gates stuck audio generation.

---

## Web Client (`web/`)

The web client is the first deployed UI and primary end-to-end test harness.

### Stack

Use **vanilla TypeScript + Vite**. The web app is a validation harness: one page,
login, microphone capture, WebSocket, transcript/status display, and playback.
Do not use Next.js or a larger app framework unless the requirements change.

### Secure context requirement

Browser microphone capture requires a secure context:

- `localhost` and `127.0.0.1` are acceptable for Phase 5 local development.
- LAN IPs, hostnames, and public URLs require HTTPS.
- Phase 7 public web validation cannot begin until Phase 6 TLS is complete.

### Required behavior

- Login form protected by allowed email + `HERMES_VOICE_WEB_PASSWORD`, followed
  by emailed numeric verification code.
- Browser session cookie after successful verification.
- Push-to-talk or record/release control.
- WebSocket connection state.
- Microphone capture using browser APIs.
- Send `start_utterance` metadata before audio bytes.
- Transcript display and chat bubbles for user and Hermes messages.
- Audio playback for backend TTS bytes.
- `assistant_text` rendering for final Hermes text.
- Turn state: idle, recording/listening, transcribing, Hermes thinking,
  still-thinking progress, speaking, awaiting approval, error.
- Cancel control for thinking, still-thinking, speaking, and active assistant
  playback.
- Audio-too-short feedback when the backend sends `voice_turn_skipped`.
- Latency timings for STT, Hermes first text, first audio, and full turn.
- Clear display of standardized backend errors.
- Readiness-gated PTT: do not enable voice capture until `session_started`
  confirms the socket session is ready.
- Manual check/reconnect control that sends `ping`, expects `pong`, and forces
  reconnect on timeout.
- Heartbeat/lifecycle recovery for stale sockets. Reconnect behavior for V1:
  show offline/checking state and start a fresh session after reconnect.

### Audio format

Browsers may naturally produce `webm/opus` instead of WAV. The backend accepts
browser formats for the harness while keeping `UPLINK_FORMAT=wav` as the mobile
V1 target. The web client's audio constraints must not force the mobile format
decision.

---

## Web Login and Public Exposure

Before exposing the web app publicly:

- Rate-limit `/login`.
- Rate-limit `/login/verify`.
- Lock out repeated failures per IP for a short window.
- Allow only configured web login emails.
- Send one-time verification codes by email after password acceptance.
- Set session cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax`.
- Use a strong random `SESSION_SECRET`.
- Consider temporary Nginx basic auth or an unguessable path prefix as
  defense-in-depth while this remains a private tool.

---

## Mobile App (`mobile/ios/HermesVoice`) - Native Swift First

**Last mobile-plan review:** 2026-04-30 Pacific.

The native Swift iOS app is intentionally deferred until the backend and web
harness are proven on Ubuntu. If any old Flutter/Dart or React Native references
appear in historical notes, treat them as superseded unless a later decision
explicitly reopens that choice.

Native Swift/SwiftUI is the selected first mobile implementation because this is
a voice-first, pocketable iPhone app whose product risk sits in iOS audio
session behavior, lock-screen constraints, headset/Bluetooth controls, low
latency playback, and Apple permission/entitlement behavior. Those are native
iOS surfaces. Flutter and React Native remain secondary options only if the app
later needs broad cross-platform UI reuse; they should not be used to validate
the first iPhone voice experience.

The mobile code stays in this repo under `mobile/ios/HermesVoice/` (or the
nearest Xcode-generated equivalent inside `mobile/ios/`). Do not create a
separate repository for the first iOS app unless repo ownership changes.

### Build environment

- Ubuntu can write, review, commit, and push Swift, SwiftUI, Xcode project
  files, docs, and non-Xcode text changes.
- Ubuntu cannot validate Xcode build settings, iOS Simulator behavior, SwiftUI
  previews, code signing, provisioning profiles, entitlements, background audio,
  lock-screen behavior, Control Center behavior, or headset/Bluetooth media
  controls.
- Final mobile validation belongs on Nick's MacBook Air with current Xcode and,
  before release, a physical iPhone.
- Uses the same backend URL and WebSocket contract proven by the web client.

### Parity before mobile-only improvements

The iOS app must first match the current web app/backend behavior. Do not add
mobile-only interaction modes until this parity checklist passes against the
same `/ws/voice` contract implemented in `web/src/app.ts`, `web/src/ws.ts`,
`web/src/types.ts`, `web/src/ui.ts`, `api/app/routes/voice.py`,
`api/app/routes/web.py`, `api/app/auth.py`, and `api/app/services/pipeline.py`.

- Auth/session: support the current backend auth story. Browser web uses
  allowed email + password + emailed verification code + `hv_session` cookie.
  Mobile may use `Authorization: Bearer <api-key>` for the
  WebSocket unless a native login flow is explicitly added later.
- Session readiness: wait for `session_started` with `conversation_id` before
  enabling push-to-talk. A reconnect creates a new session; no resume is
  promised in V1.
- Connection UX: expose Ready, Checking, and Offline-equivalent states; provide
  manual check/reconnect; send `ping` and require matching `pong`; reconnect on
  timeout or closed socket.
- Lifecycle recovery: treat foreground/resume as a reason to verify socket
  health, but avoid false reconnect loops caused by background timer throttling.
- Push-to-talk: press starts capture only from idle/ready; release stops
  capture, sends `start_utterance`, binary audio, and `end_of_utterance`.
- Audio metadata: send accepted format and sample rate before bytes. Mobile V1
  target remains `format="wav"` with 16 kHz, 16-bit, mono audio unless measured
  network results justify `ogg/opus`.
- Turn states: render `active_state` frames for `idle`, `listening`,
  `thinking`, `thinking_progress`, `speaking`, and `awaiting_approval`. The
  `thinking_progress` state is current behavior and should show non-error
  still-thinking feedback.
- Chat transcript: render user bubbles from `transcript` frames and Hermes
  bubbles from final `assistant_text` frames.
- Assistant audio: play binary TTS frames in order; clear queued/current
  playback when a cancel or reconnect occurs; ignore late audio from a canceled
  turn until the next valid turn starts.
- Cancel/interrupt: while thinking, still-thinking, speaking, or playing
  assistant audio, provide cancel. Send `{"event":"cancel_turn"}` when the
  backend turn is cancellable, optimistically return local UI to idle, and
  accept backend confirmation via `active_state=idle` and `turn_end`.
- Too-short audio: handle `voice_turn_skipped` with
  `reason="audio_too_short"` by showing visible "hold longer" feedback and
  returning to idle.
- Errors: render standardized `error` frames with code, message, and status;
  keep the socket path recoverable where possible.
- Compatibility: safely ignore unknown future JSON frames.

### Expected V1 iOS behavior

- Push-to-talk capture.
- Send `start_utterance` with `format="wav"` before audio bytes.
- 16 kHz, 16-bit, mono WAV uplink.
- Opus playback from backend TTS.
- Transcript and turn status display.
- Background/lock-screen playback through native iOS audio session APIs where
  Apple permits it.

### Mobile-only constraints and realistic options

- Pocket mode should be explicit, such as a large locked-screen-friendly PTT
  surface while the app is foregrounded, plus strong haptics/audio cues. Do not
  assume screen-off microphone capture is available.
- Headset/Bluetooth controls can be mapped to supported remote-control events
  where iOS exposes them, but behavior varies by device and app audio session.
- Audio routing must use native `AVAudioSession` category/mode/options and be
  validated with built-in speaker, wired headset if available, AirPods, and at
  least one Bluetooth device.
- Always-listening and wake-word behavior are not V1 assumptions. Safe
  alternatives are foreground PTT, an explicit "keep awake while pocket mode is
  active" setting, lock-screen playback controls for assistant audio, Shortcuts
  integration, or a manual Action Button/Siri Shortcut entry point if feasible.
- Background audio may allow playback continuity, but it does not grant a
  general always-on microphone. Treat entitlements and App Review constraints as
  product constraints, not implementation details.

### Nick's MacBook Air / Xcode validation checklist

After pulling the branch on the MacBook Air:

1. `git status --short --branch` and confirm the branch is the expected mobile
   work branch.
2. Open `mobile/ios/HermesVoice/` in Xcode, or open the generated
   `HermesVoice.xcodeproj` / `HermesVoice.xcworkspace` if present.
3. Select the HermesVoice app scheme and a current iOS Simulator target.
4. Resolve any Xcode-reported package/project migration prompts deliberately;
   commit resulting project-file changes only if they are expected.
5. Build with `Product > Build`.
6. Run in Simulator and verify launch, microphone permission prompt, network
   permission behavior if prompted, and basic UI layout.
7. Configure the backend URL/API-key mechanism without committing secrets.
8. Connect to `/ws/voice`; verify `session_started` arrives before PTT enables.
9. Perform one normal PTT turn: press, speak, release; verify transcript bubble,
   `thinking`, optional `thinking_progress`, audio playback, final
   `assistant_text` bubble, and idle return.
10. Test manual check/reconnect by disabling network or stopping the backend,
    then restoring it; verify Checking/Offline/Ready states and a new session.
11. Test cancel during thinking and during assistant playback; verify local
    playback stops and late audio is ignored.
12. Test an intentionally tiny tap; verify audio-too-short feedback and idle
    recovery.
13. Test lock-screen/background behavior on a physical iPhone: assistant audio
    playback, interruption by phone call/Siri, route changes, and return to app.
14. Test AirPods or another Bluetooth headset for recording route, playback
    route, and any available remote-control behavior.
15. Confirm signing team, bundle id, entitlements, and provisioning profile are
    valid before any TestFlight or device-distribution step.

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
LogsDirectory=hermes-voice
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
- Secure cookie/session primitives and login rate-limit design.
- Deployment prerequisites for `.env` and logs documented.

### Phase 2 - Hermes client

- Responses API streaming client, conversation id support, speakable event
  filtering, Hermes smoke test, and inter-token timeout.

### Phase 3 - Audio services and headless pipeline

- Whisper STT, TTS request wrapper, pipeline coordinator, chunking heuristic,
  cancellation behavior, smoke pipeline script.

### Phase 4 - WebSocket voice endpoint

- `/ws/voice`, `session_started`, `start_utterance`, audio metadata validation,
  turn lifecycle, cancellation, transcript/status/error frames, binary TTS.

### Phase 5 - Local web validation client

- Vanilla TypeScript + Vite client.
- Login, browser mic capture on `localhost`, record/release control, WebSocket
  client, playback, transcript/status view, latency timings.

### Phase 6 - Ubuntu deployment

- Production venv, systemd, `.env` permissions, log directory, Nginx TLS/public
  URL, WebSocket proxying, smoke checks.

### Phase 7 - Public end-to-end web validation

- Test the HTTPS web app from a browser, including mic capture, tool-using Hermes
  turns, longer conversations, reconnect behavior, and login throttling.

### Phase 8 - Native Swift iOS app on Mac

- Build the mobile app against the proven backend contract.
- Keep source under `mobile/ios/HermesVoice/`.
- Complete web/backend parity before pocket-mode, headset, or other mobile-only
  improvements.
- Validate Xcode, Simulator, signing, entitlements, background audio, and
  lock-screen behavior on Nick's MacBook Air with Xcode.

### Phase 9 - V1 reassessment

- Decide PTT vs VAD, WAV vs `OGG(Opus)`, tool-progress status frames, newer TTS
  model options, and interrupt policy based on real use.

---

## Current decisions

- **Hermes API:** local HTTP + SSE at `127.0.0.1:8642/v1`.
- **Conversation state:** owned by Hermes through `conversation`.
- **Backend state:** no transcript/history persistence in V1.
- **Initial deployed UI:** web client on Ubuntu.
- **Web stack:** vanilla TypeScript + Vite.
- **Mobile app:** native Swift/SwiftUI first, under `mobile/ios/HermesVoice/`,
  built and finally validated on Mac.
- **Mobile V1 uplink:** WAV.
- **Browser uplink:** declared per turn; likely `webm/opus`.
- **Compressed uplink option:** `OGG(Opus)`, not raw `.opus`.
- **Downlink:** Opus TTS audio.
- **Interrupt policy:** ignore extra inbound audio while a turn is active;
  explicit cancel uses `cancel_turn`, and disconnect or `new_session` cancels
  active work.
- **Reconnect policy:** reconnect starts a new session in V1.
- **Auth:** allowed email + web password + emailed verification code for browser
  UI; API key for later mobile/backend access unless native login is added.

---

## Still open after web validation

- Whether the browser client should remain as an operational admin/test tool.
- Whether mobile uplink should stay WAV after real-world network tests.
- Whether VAD improves the experience compared with push-to-talk.
- Whether tool-progress JSON frames are useful or noisy.
- Whether barge-in is worth implementing.
- Whether a newer TTS model improves first-audio latency enough to switch.
