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
- API / WebSocket: `https://api.hermes-voice.dashanddata.com`

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

1. `avatar08` runs `hermes-voice.service` binding to `0.0.0.0:8700`.
2. `avatar08` UFW allows port 8700 only from maestro04's LAN IP.
3. `maestro04` Nginx proxies `hermes-voice.dashanddata.com` → `192.168.0.244:8700`.
4. `maestro04` Nginx proxies `api.hermes-voice.dashanddata.com` → `192.168.0.244:8700`
   with WebSocket upgrade headers.
5. Certbot manages TLS for both domains on maestro04.

See `docs/` for full deployment runbook.

## Service operations

```bash
# On avatar08
sudo systemctl status hermes-voice
sudo systemctl restart hermes-voice
sudo journalctl -u hermes-voice -f
tail -f /var/log/hermes-voice/hermes_voice_api.log
```

## Rollback

Stop service, checkout previous commit, reinstall dependencies, restart service.
