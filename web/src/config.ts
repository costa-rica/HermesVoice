// Detect whether we're running in production (HTTPS on public domain)
// vs local development (localhost through Vite proxy).

// Use the same origin for WebSocket connections in both production and local dev.
// This avoids requiring a separate TLS certificate for api.hermes-voice.dashanddata.com
// and lets the existing nginx host proxy /ws/* to the API.
export const WS_BASE_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;

export const WS_VOICE_URL = `${WS_BASE_URL}/ws/voice`;

// Login/logout are always same-origin (proxied in dev, direct in prod)
export const LOGIN_URL = '/login';
export const LOGOUT_URL = '/logout';
