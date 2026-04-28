# HermesVoice — Project Plan V02

**Date:** 2026-04-27
**Supersedes:** `HermesVoice-Plan.md`
**Host of record:** `avatar08` (FSDC, Ubuntu)

A real-time voice conversation layer for Hermes Agent, built as a monorepo with a FastAPI backend and a Flutter mobile app. V02 incorporates verified facts about Hermes' built-in OpenAI-compatible API server (now running on this host) and removes the open questions that were resolved during the assessment phase.

---

## What changed since V01

V01 left several things speculative. They are now confirmed:

- **Hermes ships an OpenAI-compatible HTTP API server** (`gateway/platforms/api_server.py`) — no plugin install, just env-var activation.
- **It is now live on `avatar08`** at `http://127.0.0.1:8642` with bearer auth, after enabling `API_SERVER_ENABLED=true` and `API_SERVER_KEY=...` in `~/.hermes/.env` and restarting the gateway. Verified by a successful `POST /v1/chat/completions`.
- **Streaming wire format is SSE**, not WebSocket. The OpenAI SDK abstracts this — no protocol work in the backend.
- **The Responses API** (`POST /v1/responses` with `conversation` or `previous_response_id`) is preferred for multi-turn voice — Hermes stores tool history server-side, so the backend only ships the latest utterance per turn.
- **Hermes' agent loop owns memory, tools, and skills.** The backend is a thin pipe; it does not need to maintain `conversation_history`.
- **No WebSocket between backend and Hermes.** WebSocket stays on the phone↔backend hop only.

V02 reflects this throughout.

---

## Architecture & Data Flow

```
[Flutter App on iPhone]
    │
    │  1. Capture mic audio in real-time chunks
    │  2. Stream PCM/Opus over WebSocket  ─────────┐
    ▼                                              │ phone ↔ backend
[FastAPI Backend — WS /ws/voice]                   │ (the only WebSocket)
    │                                              │
    │  3. Buffer until end-of-utterance            │
    │  4. POST audio → OpenAI Whisper  → transcript
    │  5. POST transcript → Hermes /v1/responses    ─── (HTTP + SSE)
    │       conversation: "<session_id>"            ─── server-side state
    │  6. Receive token deltas via SSE
    │  7. Stream deltas → OpenAI TTS (chunked)
    │  8. Pipe TTS audio bytes back over WS  ──────┘
    ▼
[Flutter App]
    │  9. Play audio chunks as they arrive
```

**Latency principle:** Steps 5–8 are pipelined. As soon as Hermes emits the first token over SSE, the backend feeds it to TTS and starts shipping audio bytes to the phone. The user starts hearing a response while Hermes is still generating.

---

## Monorepo Structure

```
hermes-voice/
├── api/                              # FastAPI backend
│   ├── app/
│   │   ├── main.py                   # App entrypoint, routes, lifespan
│   │   ├── config.py                 # pydantic-settings from .env
│   │   ├── auth.py                   # API key middleware (phone → backend)
│   │   ├── routes/
│   │   │   └── voice.py              # WebSocket /ws/voice endpoint
│   │   └── services/
│   │       ├── stt.py                # OpenAI Whisper client
│   │       ├── hermes.py             # Hermes Responses API client (streaming)
│   │       ├── tts.py                # OpenAI TTS client (streaming)
│   │       └── pipeline.py           # Pipelined STT → Hermes → TTS coordinator
│   ├── tests/
│   │   ├── test_hermes_smoke.py      # Hits real Hermes on 8642
│   │   └── test_pipeline_text.py     # Text-only pipeline (skip audio I/O)
│   ├── .env.example
│   ├── requirements.txt
│   └── README.md
│
├── mobile/                           # Flutter iOS app
│   ├── lib/
│   │   ├── main.dart
│   │   ├── screens/
│   │   │   └── conversation_screen.dart
│   │   └── services/
│   │       ├── audio_service.dart    # Mic capture + speaker playback
│   │       └── websocket_service.dart
│   ├── ios/                          # Xcode project
│   ├── pubspec.yaml
│   └── README.md
│
├── scripts/
│   ├── smoke_hermes.sh               # curl /v1/chat/completions
│   └── smoke_pipeline.py             # Text → Hermes → TTS → wav file
├── .gitignore
└── README.md
```

---

## Backend — FastAPI (`api/`)

### Tech stack

| Concern | Library | Notes |
|---|---|---|
| Framework | FastAPI | |
| WebSocket | FastAPI native | phone ↔ backend only |
| STT | `openai` SDK → Whisper | `whisper-1` (or local Groq if added later) |
| LLM | `openai` SDK → Hermes | `base_url=http://127.0.0.1:8642/v1` |
| TTS | `openai` SDK → TTS | `tts-1` streaming, mp3/opus output |
| Config | `pydantic-settings` | |
| HTTP client | `httpx` | for any non-OpenAI calls |
| Process manager | systemd | matches existing avatar08 setup |

### Configuration (`api/.env.example`)

```env
# Auth between Flutter app and this backend
HERMES_VOICE_API_KEY=generate-with-openssl-rand-hex-32

# OpenAI for STT + TTS
OPENAI_API_KEY=sk-...

# Hermes (running locally on avatar08)
HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<value of API_SERVER_KEY in ~/.hermes/.env>
HERMES_MODEL=hermes-agent

# Optional tuning
STT_MODEL=whisper-1
TTS_MODEL=tts-1
TTS_VOICE=alloy
TTS_FORMAT=opus            # opus is lower-latency than mp3
HERMES_REQUEST_TIMEOUT=600 # Hermes turns can take >30s with tool use
```

### Hermes client (`services/hermes.py`)

Use the OpenAI SDK pointed at Hermes. Prefer the **Responses API with `conversation`** so the backend doesn't have to track or replay history — Hermes does it, and tool calls/results stay server-side:

```python
# services/hermes.py
from openai import AsyncOpenAI
from app.config import settings

_client = AsyncOpenAI(
    base_url=settings.HERMES_BASE_URL,
    api_key=settings.HERMES_API_KEY,
    timeout=settings.HERMES_REQUEST_TIMEOUT,
)

async def stream_response(text: str, conversation_id: str):
    """Yield text deltas as Hermes generates them."""
    stream = await _client.responses.create(
        model=settings.HERMES_MODEL,
        input=text,
        conversation=conversation_id,   # server-side multi-turn
        stream=True,
    )
    async for event in stream:
        # Filter for token deltas; ignore tool-progress events for TTS
        if event.type == "response.output_text.delta":
            yield event.delta
```

Notes from the API server source:
- Streaming events include `response.created`, `response.output_text.delta`, `response.output_item.added/done`, `response.completed`, plus tool-progress events. Only feed `output_text.delta` to TTS — don't speak `"running terminal..."`.
- `model` field is cosmetic; Hermes uses whatever is in `~/.hermes/config.yaml`.
- 30s+ turns are normal when Hermes invokes tools. Long timeout is mandatory.

### Pipeline coordinator (`services/pipeline.py`)

The pipeline batches token deltas into TTS-friendly chunks (sentence boundaries or N tokens) so TTS isn't called once per word:

```python
async def voice_turn(audio_in: bytes, conversation_id: str, ws):
    transcript = await stt.transcribe(audio_in)

    buffer = ""
    async for delta in hermes.stream_response(transcript, conversation_id):
        buffer += delta
        if _sentence_boundary(buffer):
            async for audio_chunk in tts.synthesize_stream(buffer):
                await ws.send_bytes(audio_chunk)
            buffer = ""
    if buffer:
        async for audio_chunk in tts.synthesize_stream(buffer):
            await ws.send_bytes(audio_chunk)
    await ws.send_json({"event": "turn_end"})
```

### WebSocket endpoint (`routes/voice.py`)

```
WS /ws/voice?api_key=<HERMES_VOICE_API_KEY>
```

- **Inbound:** binary audio chunks; JSON control frames (`{"event":"end_of_utterance"}`, `{"event":"new_session"}`).
- **Outbound:** binary TTS audio; JSON status frames (`{"event":"transcript", "text":...}`, `{"event":"turn_end"}`, `{"event":"error", ...}`).
- One WebSocket = one `conversation_id`. New session ⇒ new UUID; Hermes treats it as a fresh chain.

### Auth

- **Phone → backend:** `HERMES_VOICE_API_KEY` validated on connect (query param now, header on the iOS-Flutter side via custom WebSocket headers later).
- **Backend → Hermes:** `HERMES_API_KEY` (= `API_SERVER_KEY` from `~/.hermes/.env`) sent as `Authorization: Bearer ...` by the OpenAI SDK.
- Hermes is bound to `127.0.0.1` only. It must never be exposed on the LAN — its toolset includes terminal access. If the Flutter app needs to reach the backend from outside the network, terminate TLS + auth at FastAPI (Nginx + Let's Encrypt), never at Hermes.

---

## Mobile App — Flutter (`mobile/`)

Unchanged from V01 except for the WebSocket message contract:

| Concern | Package |
|---|---|
| Audio capture | `record` |
| Audio playback | `just_audio` |
| WebSocket | `web_socket_channel` |
| Background audio | `audio_session` |

### Behaviour
- Launch → connect WS with `api_key` query param
- Push-to-talk (V1): hold to record, release sends `{"event":"end_of_utterance"}`
- Receive audio frames → play through `just_audio` as they arrive
- Receive `{"event":"turn_end"}` → re-arm mic
- Background: configure `AVAudioSessionCategory.playAndRecord` so playback survives screen lock

### iOS deployment
Direct Xcode install. Free Apple ID = 7-day re-sign cycle; paid Developer account ($99/yr) = 1 year. No TestFlight required.

---

## Conversation State

**Owned by Hermes**, not the backend. Each WebSocket session generates a `conversation_id` (UUID). The backend passes it as `conversation: "<id>"` on every `/v1/responses` call. Hermes:
- Stores the response chain in SQLite (`gateway` profile DB).
- Preserves tool calls + outputs across turns.
- Caps stored responses at 100 LRU per profile.

If the WebSocket drops and reconnects with the same `conversation_id`, Hermes resumes the same chain. If a fresh chain is desired, the client sends `{"event":"new_session"}` and the backend mints a new UUID.

The backend keeps **no transcripts and no history** — Hermes is the source of truth. This is a deliberate simplification from V01.

---

## Deployment

### Hermes (already done on avatar08)

`~/.hermes/.env` now contains:
```
API_SERVER_ENABLED=true
API_SERVER_KEY=<32-byte hex>
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
```
Verified: `ss -tlnp | grep 8642` shows the listener; `[Api_Server] API server listening on http://127.0.0.1:8642 (model: hermes-agent)` in `~/.hermes/logs/agent.log`; `POST /v1/chat/completions` returns valid OpenAI-format responses.

Operationally:
- Hermes runs under the existing `hermes gateway` user-service. `hermes gateway restart` cycles it.
- Do **not** change `API_SERVER_HOST` to `0.0.0.0`. The API server gives the caller full terminal access — keep it loopback-only.

### HermesVoice backend (systemd on avatar08)

```ini
# /etc/systemd/system/hermes-voice.service
[Unit]
Description=HermesVoice API
After=network.target hermes-gateway.service
Wants=hermes-gateway.service

[Service]
User=limited_user
WorkingDirectory=/opt/hermes-voice/api
EnvironmentFile=/opt/hermes-voice/api/.env
ExecStart=/opt/hermes-voice/api/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8700
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Expose port 8700 through the existing Nginx reverse proxy with SSL if the phone needs to reach it from outside the FSDC network. Keep Hermes loopback.

---

## Development Phases

### Phase 0 — Hermes API server (DONE 2026-04-27)
- ✅ Enabled `API_SERVER_*` in `~/.hermes/.env`
- ✅ Restarted gateway, verified listener on `127.0.0.1:8642`
- ✅ Smoke-tested `POST /v1/chat/completions` end-to-end

### Phase 1 — Backend foundation (1–2 days)
- Monorepo skeleton (`api/`, `mobile/`, `scripts/`, `.gitignore`)
- FastAPI app with pydantic-settings config and API-key middleware
- `services/hermes.py` using the OpenAI SDK (Responses API + streaming)
- `scripts/smoke_hermes.sh` — verifies env + Hermes connectivity
- `tests/test_hermes_smoke.py` — pytest hits real local Hermes
- Stub WS endpoint that echoes binary frames

### Phase 2 — Voice pipeline (2–3 days)
- `services/stt.py` — Whisper transcription of buffered audio
- `services/tts.py` — TTS streaming chunks (opus)
- `services/pipeline.py` — sentence-boundary chunking, SSE → TTS pipelining
- `scripts/smoke_pipeline.py` — text-in, wav-out, no WebSocket; proves the chain works headless
- Wire the WS endpoint to `pipeline.voice_turn`

### Phase 3 — Flutter app (3–5 days)
- Flutter project, WebSocket service, audio service
- Push-to-talk UI with talking indicator + transcript display
- End-to-end test on a physical iPhone over the FSDC LAN

### Phase 4 — Background audio & polish (1–2 days)
- `audio_session` config for screen-locked playback
- Reconnect/back-off logic
- Optional: VAD-based hands-free mode (replaces push-to-talk)

### Phase 5 — Production hardening (1–2 days)
- Nginx + SSL terminator on port 443 → backend 8700 (only if remote access is needed)
- Systemd unit + log rotation
- Rate limiting on the WS endpoint
- Per-session timeout / idle disconnect

---

## Resolved questions (formerly "Open Questions")

1. **What port is Hermes' API server on?** `127.0.0.1:8642`. Confirmed listening.
2. **Is `hermes gateway` already running as a service?** Yes — managed as a systemd user-service (`hermes gateway restart` cycles it).
3. **Does Hermes speak HTTP or WebSocket?** HTTP only. Streaming is SSE. WebSocket stays on the phone↔backend hop.
4. **How is conversation state handled?** Server-side in Hermes via the Responses API `conversation` parameter. Backend stores nothing.

## V1 implementation decisions (kept revisable)

Each decision below picks the simplest thing that works on `avatar08` today, and identifies the seam where we'd change direction later. None of these locks us out of the "right" long-term answer.

### End-of-utterance detection — Push-to-talk

**V1:** Flutter PTT button. On release, the app sends `{"event":"end_of_utterance"}` over the WS; the backend treats that frame as the boundary and runs the pipeline against everything buffered since the previous boundary.

**Seam for change:** The backend never inspects audio energy or decides on its own when speech ended — it only reacts to the control frame. Swapping to VAD (WebRTC VAD or Silero) in Phase 4+ is purely a Flutter-side change: replace the button-press source of the frame with a VAD callback. No backend work required. If we later want server-side VAD, we add a `services/vad.py` that emits the same internal "utterance-complete" event that the WS handler already produces.

**Discovery before V2:** When PTT works end-to-end, run a few sessions with conversational pacing and note where users instinctively pause — that decides whether VAD adds value or just adds error.

### Audio format on the wire — PCM WAV up, Opus down

**V1 uplink (phone → backend):** 16 kHz, 16-bit, mono PCM wrapped in WAV. Whisper accepts WAV natively (no transcoding on the backend), it is trivial to dump to disk for debugging, and Flutter `record` produces it with no extra codec wiring. On a LAN this is ~32 kB/s — bandwidth is not a concern for V1.

**V1 downlink (backend → phone):** Opus (`TTS_FORMAT=opus` in `.env`). OpenAI TTS streams Opus frames directly; `just_audio` plays them with no transcoding.

**Seam for change:** Define the codec in one place — `api/app/config.py` (`UPLINK_FORMAT`, `DOWNLINK_FORMAT`) and a matching constant in the Flutter app. The STT service reads bytes + format from the config; switching uplink to Opus is changing one enum and re-running the smoke test. Whisper also accepts Opus/OGG, so the transcription side is format-agnostic.

**Discovery path (do before locking it in):** Add `scripts/smoke_whisper.py` that POSTs a fixture WAV to Whisper and prints (transcript, latency, $ cost). If round-trip latency on a 3-second utterance is acceptable, we are done. If WAV bandwidth bites later (e.g. cellular usage), flip `UPLINK_FORMAT=opus`.

### Tool-progress UX — silent filter, single seam

**V1:** The Hermes Responses stream emits `response.output_text.delta` (speakable), `response.output_item.added/done`, `response.tool.progress`, `function_call*`, etc. The pipeline filters with one predicate:

```python
def is_speakable_event(event) -> bool:
    return event.type == "response.output_text.delta"
```

Everything else is dropped on the floor in V1.

**Seam for change:** Because the predicate is the only filter, surfacing "Hermes is running terminal..." in V2 is purely additive — feed non-speakable events into a small classifier that maps them to `{"event":"tool_progress","label":...}` JSON frames on the same WebSocket. No refactor of the speakable path. The Flutter side can ignore unknown JSON frames safely, so the backend can ship the new frame before the app understands it.

### Per-utterance timeout / interrupt — ignore in V1, cancellable underneath

**V1 policy:** While a turn is being generated or spoken, the Flutter PTT button is visually disabled and any inbound audio frames are dropped. The user waits for `{"event":"turn_end"}` before the next turn. This avoids the hardest part of full-duplex voice (echo cancellation, barge-in arbitration) entirely.

**Seam for change:** Even though V1 ignores barge-in, structure the pipeline so cancellation is free later:
- `voice_turn(...)` runs as an `asyncio.Task` stored on the WS session.
- A `cancel_turn()` method cancels the task; the Hermes SSE stream and the in-flight TTS request both honour cancellation (httpx + the OpenAI SDK propagate it).
- Add `INTERRUPT_POLICY` to settings with values `ignore` (V1 default), `cancel` (cancel current turn on new utterance), `queue` (run next turn after current one). Only `ignore` is wired in V1; the other two are switch-cases over the same task handle.

**Per-turn timeout:** Hermes can run minutes on tool-heavy turns, so do not impose a wall-clock cap on the LLM call itself — `HERMES_REQUEST_TIMEOUT=600` already covers it. Add a separate `IDLE_TIMEOUT` (default 120 s) on the WS session for "no traffic at all in either direction" — that one is safe to enforce because it cannot cut off legitimate work.

**Discovery path:** During Phase 3 testing, observe real turn lengths and whether testers naturally try to interrupt. If they do, flip `INTERRUPT_POLICY=cancel`; if not, leave it.

---

## Still-open (after V1 is real)

These are deliberately not answered now — the V1 build will give us cheap evidence:

- Whether PTT vs VAD is the right interaction for this specific use case (re-evaluate after Phase 3 dogfooding).
- Whether uplink WAV bandwidth matters in practice (re-evaluate after first remote/cellular session).
- Whether tool-progress indicators improve the UX or just add chatter (decide after observing 10+ tool-using turns).
- Whether barge-in is worth the echo-cancellation work (decide after users actually try it).

---

## Reference: working curl

For documentation and CI smoke tests:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2-)

# Non-streaming
curl -sS http://127.0.0.1:8642/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"ping"}]}'

# Streaming (Responses API, recommended for HermesVoice)
curl -N http://127.0.0.1:8642/v1/responses \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","input":"ping","conversation":"smoke","stream":true}'
```
