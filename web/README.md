# HermesVoice Web Client

Vanilla TypeScript + Vite browser validation harness.

## Dev server (localhost only for mic access)

```bash
npm install
npm run dev
# Opens at http://localhost:5173
# Proxies /api/*, /health, /login, /logout, /ws/* to http://127.0.0.1:8700
```

The backend must be running:

```bash
cd ../api
uvicorn app.main:app --host 127.0.0.1 --port 8700 --reload
```

## Build for production

```bash
npm run build
# Output: dist/
```

The built `dist/` is served by the FastAPI backend via StaticFiles.

## Browser mic capture note

Mic capture requires `localhost`, `127.0.0.1`, or HTTPS.
Do not test against a LAN IP without TLS — mic access will be silently denied.
