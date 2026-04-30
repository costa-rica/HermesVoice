# HermesVoice avatar08 API/Web Runbook

This document records the current HermesVoice API/web deployment on the FSDC network and the key changes needed to get it running on avatar08 behind the maestro04 Nginx proxy.

## Current topology

- **Application host:** `avatar08`, Ubuntu server on the FSDC LAN.
- **Application path:** `/home/limited_user/applications/HermesVoice/`.
- **Service user:** `limited_user`.
- **API service:** `hermesvoice-api.service`.
- **API bind:** `0.0.0.0:8700` on avatar08.
- **Public host:** `https://hermes-voice.dashanddata.com/`.
- **Reverse proxy host:** `maestro04`.
- **Proxy target:** `http://192.168.0.244:8700`.
- **Hermes Agent upstream:** `http://127.0.0.1:8642/v1` from avatar08. Do not expose this port publicly.
- **Log file for TheServerManager:** `/home/limited_user/logs/hermes_voice_api.log`.

The browser app is a Vite static build generated under `web/dist/`. There is no separate web systemd service in the current deployment. The FastAPI service serves the web assets and API/WebSocket endpoints, while maestro04 terminates TLS and proxies traffic to avatar08 port `8700`.

## Repository layout used by deployment

```text
api/      FastAPI backend and WebSocket voice pipeline
web/      Browser validation client built with Vite/TypeScript
deploy/   systemd and Nginx reference deployment files
docs/     requirements, plans, and this runbook
```

## Production environment file

The API reads `api/.env` relative to its working directory. Do not commit this file or print its secret values.

Required production settings include:

```env
NAME_APP=hermes_voice_api
RUN_ENVIRONMENT=production
PATH_TO_LOGS=/home/limited_user/logs

HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_MODEL=hermes-agent

# secret values, stored only in api/.env
HERMES_VOICE_WEB_PASSWORD=<strong-password>
HERMES_VOICE_WEB_EMAILS=<allowed-login-email>
HERMES_VOICE_SMTP_HOST=<smtp-host>
HERMES_VOICE_SMTP_PORT=587
HERMES_VOICE_SMTP_USERNAME=<smtp-username>
HERMES_VOICE_SMTP_PASSWORD=<smtp-password>
HERMES_VOICE_SMTP_FROM_EMAIL=<from-address>
HERMES_VOICE_API_KEY=<generated-token>
SESSION_SECRET=<generated-token>
OPENAI_API_KEY=<valid-openai-key>
HERMES_API_KEY=<avatar08-hermes-api-server-key>
```

Important notes:

- `RUN_ENVIRONMENT=production` is required for file logging. When the app was left in `development`, TheServerManager could not find `/home/limited_user/logs/hermes_voice_api.log` because the app only logged to stderr.
- Browser login requires an allowed email address, the web password, and the emailed verification code. `HERMES_VOICE_WEB_EMAILS` may contain one address or multiple comma-separated addresses.
- `OPENAI_API_KEY` must be a real key. A placeholder key allows login/WebSocket connection but fails during STT with `401 invalid_api_key` and the browser shows `[INTERNAL_ERROR] Voice turn failed`.
- Keep `.env` owned/readable by `limited_user`, for example:

```bash
sudo chown limited_user:limited_user /home/limited_user/applications/HermesVoice/api/.env
sudo chmod 640 /home/limited_user/applications/HermesVoice/api/.env
```

## Build and run on avatar08

Install/update Python dependencies:

```bash
cd /home/limited_user/applications/HermesVoice/api
/home/limited_user/environments/hermes_voice/bin/pip install -r requirements.txt
```

Build the browser app:

```bash
cd /home/limited_user/applications/HermesVoice/web
npm install
npm run build
```

Run the API manually for local debugging:

```bash
cd /home/limited_user/applications/HermesVoice/api
/home/limited_user/environments/hermes_voice/bin/python \
  -m uvicorn app.main:app --host 0.0.0.0 --port 8700
```

## systemd service on avatar08

Current service name:

```text
hermesvoice-api.service
```

The important details are:

```ini
[Service]
User=limited_user
Group=limited_user
WorkingDirectory=/home/limited_user/applications/HermesVoice/api
ExecStart=/home/limited_user/environments/hermes_voice/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8700
Restart=always
```

The `WorkingDirectory` must be the `api/` directory so `pydantic-settings` can read `api/.env`. The correct Python module is `app.main:app`; using `src.main:app` fails with `ModuleNotFoundError: No module named 'src'`.

Service commands:

```bash
sudo systemctl daemon-reload
sudo systemctl restart hermesvoice-api.service
sudo systemctl status hermesvoice-api.service --no-pager -l
sudo journalctl -u hermesvoice-api.service -n 100 --no-pager
```

TheServerManager uses narrow passwordless sudo rules from these CSV files:

```text
/home/limited_user/limited_user-systemctl.csv
/home/nick/nick-systemctl.csv
```

Rows were added for `hermesvoice-api.service` actions `start`, `stop`, `restart`, `status`, `enable`, and `disable`. The CSV changes must be applied through:

```bash
/home/nick/update-nick-systemctl.sh
```

## Nginx on maestro04

The public site is configured in:

```text
/etc/nginx/sites-available/hermes-voice.dashanddata.com
```

The HTTPS server block should proxy normal HTTP traffic and WebSocket traffic to avatar08. The WebSocket block must be inside the existing `listen 443 ssl` `server { ... }` block, before the generic `location /` block:

```nginx
location /ws/ {
    proxy_pass http://192.168.0.244:8700;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}

location / {
    proxy_pass http://192.168.0.244:8700;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}
```

After editing Nginx on maestro04:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

The port 80 Certbot redirect block should not be edited for the WebSocket fix.

## WebSocket URL decision

The browser client uses a same-origin WebSocket URL in production:

```ts
wss://hermes-voice.dashanddata.com/ws/voice
```

This was chosen instead of `wss://api.hermes-voice.dashanddata.com/ws/voice` because the `api.hermes-voice.dashanddata.com` hostname did not have a matching TLS certificate. Same-origin WebSockets are a stable long-term solution for testing and early production because they avoid separate API-subdomain certificate, cookie, and CORS complexity.

## Verification commands

Health endpoint:

```bash
curl -i https://hermes-voice.dashanddata.com/health/live
curl -i https://hermes-voice.dashanddata.com/health/ready
```

Direct backend WebSocket test on avatar08:

```bash
curl -i --max-time 10 \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Origin: https://hermes-voice.dashanddata.com' \
  http://127.0.0.1:8700/ws/voice
```

A `101 Switching Protocols` response, even followed by an auth error frame, proves the backend WebSocket route is registered and alive.

Public same-origin WebSocket test through maestro04:

```bash
curl -i --max-time 10 \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Origin: https://hermes-voice.dashanddata.com' \
  https://hermes-voice.dashanddata.com/ws/voice
```

Expected: `101 Switching Protocols`. A plain HTTP `404 Not Found` from this public URL while the direct backend test returns `101` means Nginx is not proxying `/ws/` correctly or has not been reloaded.

Browser validation:

1. Open `https://hermes-voice.dashanddata.com/`.
2. Log in with `HERMES_VOICE_WEB_PASSWORD`.
3. Confirm the status changes to `Connected`.
4. Press and hold **Hold to Talk**, speak, and release.
5. Confirm transcript, Hermes response audio, and latency updates appear.

## Troubleshooting history

- `.env` permissions initially blocked service startup with `Permission denied: '.env'`. Fixed by making `api/.env` readable by `limited_user` and setting the service `WorkingDirectory` to `api/`.
- The first `hermesvoice-api.service` attempt used `src.main:app`, which failed. The correct module path is `app.main:app`.
- TSM log discovery failed until `RUN_ENVIRONMENT=production` and `PATH_TO_LOGS=/home/limited_user/logs` were set.
- Browser WebSocket initially targeted `api.hermes-voice.dashanddata.com`; that failed because the certificate did not match the API subdomain. The web client now uses same-origin `/ws/voice`.
- Public `/ws/voice` returned `404` until maestro04 Nginx received a dedicated `/ws/` location with WebSocket upgrade headers.
- `[INTERNAL_ERROR] Voice turn failed` after audio upload was caused by an invalid placeholder `OPENAI_API_KEY`; replacing it with a valid key fixed STT.

## Rollback

```bash
cd /home/limited_user/applications/HermesVoice
git checkout <previous-good-commit>
cd api && /home/limited_user/environments/hermes_voice/bin/pip install -r requirements.txt
cd ../web && npm install && npm run build
sudo systemctl restart hermesvoice-api.service
sudo systemctl status hermesvoice-api.service --no-pager -l
```
