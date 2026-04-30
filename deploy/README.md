# HermesVoice Deployment

## avatar08 — service setup

### 1. Install dependencies into production venv

```bash
cd /home/limited_user/applications/HermesVoice/api
/home/limited_user/environments/hermes_voice/bin/pip install -r requirements.txt
```

### 2. Build the web app

```bash
cd /home/limited_user/applications/HermesVoice/web
npm install
npm run build
```

### 3. Prepare the production `.env`

```bash
cp /home/limited_user/applications/HermesVoice/api/.env.example \
   /home/limited_user/applications/HermesVoice/api/.env

# Edit .env — set all required values, then:
sudo chown limited_user:limited_user /home/limited_user/applications/HermesVoice/api/.env
chmod 640 /home/limited_user/applications/HermesVoice/api/.env
```

Required production values to rotate from dev defaults:
- `SESSION_SECRET` — generate with `openssl rand -hex 32`
- `HERMES_VOICE_WEB_PASSWORD` — choose a strong password
- `HERMES_VOICE_WEB_EMAILS` — comma-separated allowed login email addresses
- `HERMES_VOICE_SMTP_HOST`, `HERMES_VOICE_SMTP_PORT`,
  `HERMES_VOICE_SMTP_USERNAME`, `HERMES_VOICE_SMTP_PASSWORD`,
  `HERMES_VOICE_SMTP_FROM_EMAIL` — SMTP settings for login verification codes
- `HERMES_VOICE_API_KEY` — generate with `openssl rand -hex 32`
- `OPENAI_API_KEY` — real OpenAI key (placeholder causes STT 401 errors)
- `HERMES_API_KEY` — from `~/.hermes/.env` API_SERVER_KEY
- `RUN_ENVIRONMENT=production` — required for file logging
- `PATH_TO_LOGS=/home/limited_user/logs` — TheServerManager log discovery path

### 4. Ensure log directory exists

```bash
mkdir -p /home/limited_user/logs
```

### 5. Install and start the systemd service

```bash
sudo cp /home/limited_user/applications/HermesVoice/deploy/hermesvoice-api.service \
        /etc/systemd/system/hermesvoice-api.service
sudo systemctl daemon-reload
sudo systemctl enable hermesvoice-api.service
sudo systemctl start hermesvoice-api.service
sudo systemctl status hermesvoice-api.service --no-pager -l
```

### 6. UFW firewall — allow port 8700 from maestro04 only

Find maestro04's LAN IP first, then:

```bash
sudo ufw allow from <maestro04-lan-ip> to any port 8700
# Verify port 8700 is NOT open from anywhere else
sudo ufw status numbered
```

## maestro04 — Nginx setup

The reference Nginx config is `deploy/nginx-hermes-voice.conf`. The current production
deployment uses a single `hermes-voice.dashanddata.com` virtual host with same-origin
WebSocket proxying. The `api.hermes-voice.dashanddata.com` block in the reference config
is not active; it can be added later if a separate API subdomain is needed.

### 1. Copy the relevant server blocks into the existing Nginx site config

```
/etc/nginx/sites-available/hermes-voice.dashanddata.com
```

The `location /ws/` block must appear before the generic `location /` block inside
the `listen 443 ssl` server block.

### 2. Issue TLS certificates

```bash
sudo certbot --nginx -d hermes-voice.dashanddata.com
sudo certbot renew --dry-run
```

### 3. Reload Nginx

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4. DNS

Point `hermes-voice.dashanddata.com` to the FSDC public IP routed to maestro04.

## Service operations (avatar08)

```bash
sudo systemctl status hermesvoice-api.service --no-pager -l
sudo systemctl restart hermesvoice-api.service
sudo journalctl -u hermesvoice-api.service -n 100 --no-pager
tail -f /home/limited_user/logs/hermes_voice_api.log
```

## Smoke tests (post-deploy)

```bash
# Health
curl -i https://hermes-voice.dashanddata.com/health/live
curl -i https://hermes-voice.dashanddata.com/health/ready

# WebSocket upgrade (expect 101)
curl -i --max-time 10 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Origin: https://hermes-voice.dashanddata.com' \
  https://hermes-voice.dashanddata.com/ws/voice

# Hermes connectivity (on avatar08)
cd /home/limited_user/applications/HermesVoice
HERMES_BASE_URL=http://127.0.0.1:8642/v1 \
HERMES_API_KEY=<from ~/.hermes/.env API_SERVER_KEY> \
/home/limited_user/environments/hermes_voice/bin/python \
    scripts/smoke_responses_stream.py --no-tools
```

## Rollback

```bash
sudo systemctl stop hermesvoice-api.service
cd /home/limited_user/applications/HermesVoice
git checkout <previous-commit>
/home/limited_user/environments/hermes_voice/bin/pip install -r api/requirements.txt
cd web && npm run build
sudo systemctl start hermesvoice-api.service
sudo systemctl status hermesvoice-api.service --no-pager -l
```
