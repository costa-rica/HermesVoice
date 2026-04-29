# HermesVoice

Real-time voice conversation layer for Hermes Agent.

## Overview

HermesVoice connects browser and mobile clients to Hermes Agent via a FastAPI
WebSocket backend. It handles speech-to-text (OpenAI Whisper), conversation
(Hermes Responses API), and text-to-speech (OpenAI TTS), streaming audio back
to the client in near-real-time using a chunked TTS approach.

## Host assumptions

- **avatar08** (`192.168.0.244`) — Ubuntu host where this service runs.
- **Hermes** listens loopback-only at `127.0.0.1:8642`. Never expose this port.
- **maestro04** — Nginx reverse proxy that terminates TLS and forwards traffic
  to `avatar08:8700`.

## Public URLs

- Web app: `https://hermes-voice.dashanddata.com`
- API / WebSocket: same-origin under `https://hermes-voice.dashanddata.com`
  (including `wss://hermes-voice.dashanddata.com/ws/voice`).

## Secure-context rule

Browser microphone capture only works on `localhost`, `127.0.0.1`, or HTTPS.
Do not test against a LAN IP or hostname without TLS — mic access will be
silently denied.

## Monorepo structure

```
api/      FastAPI backend (Python)
web/      Browser validation client (TypeScript + Vite)
mobile/   Flutter iOS app (built later on Mac)
scripts/  Smoke-test utilities
docs/     Plans, requirements, standards
```

## Local development setup

```bash
# 1. Production Python environment (created once)
python3 -m venv /home/limited_user/environments/hermes_voice
source /home/limited_user/environments/hermes_voice/bin/activate
pip install -r api/requirements.txt

# 2. Copy and edit environment file
cp api/.env.example api/.env
chmod 600 api/.env
# Fill in OPENAI_API_KEY, SESSION_SECRET, HERMES_VOICE_WEB_PASSWORD, etc.

# 3. Start development server
cd api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8700

# 4. Start web development server (separate terminal)
cd web
npm install
npm run dev
# Opens at http://localhost:5173 (proxies /api/* and /ws/* to :8700)
```

## Smoke tests

```bash
# Hermes Responses streaming
export HERMES_BASE_URL=http://127.0.0.1:8642/v1
export HERMES_API_KEY=<from ~/.hermes/.env API_SERVER_KEY>
python scripts/smoke_responses_stream.py --no-tools

# Whisper transcription
export OPENAI_API_KEY=sk-...
python scripts/smoke_whisper.py --generate wav

# Full pipeline (text-in, audio-file-out)
python scripts/smoke_pipeline.py --text "Hello from HermesVoice"
```

## Reverse-proxy deployment (maestro04 → avatar08)

1. `avatar08` runs `hermesvoice-api.service` binding to `0.0.0.0:8700`.
2. `avatar08` UFW allows port 8700 only from maestro04's LAN IP.
3. `maestro04` Nginx proxies `hermes-voice.dashanddata.com` → `192.168.0.244:8700`.
4. The browser client uses same-origin WebSockets at `/ws/voice`; the HTTPS
   Nginx server block must include a dedicated `location /ws/` with WebSocket
   upgrade headers before the generic `location /`.
5. Certbot manages TLS for `hermes-voice.dashanddata.com` on maestro04.

See `docs/avatar08-api-web-runbook.md` for the current deployment runbook and troubleshooting history.

## Service operations

```bash
# On avatar08
sudo systemctl status hermesvoice-api.service --no-pager -l
sudo systemctl restart hermesvoice-api.service
sudo journalctl -u hermesvoice-api.service -f
tail -f /home/limited_user/logs/hermes_voice_api.log
```

## Rollback

Stop service, checkout previous commit, reinstall dependencies, restart service.
