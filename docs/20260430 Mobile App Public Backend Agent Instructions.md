# HermesVoice Mobile App Agent Instructions — Public Backend Testing

Use these instructions when building the HermesVoice mobile app from the Mac development environment.

## Goal

Build and test the mobile app against the existing public HermesVoice backend. Do not require a local Python/FastAPI backend for normal mobile development unless you are explicitly changing backend behavior.

## Backend to use

Use the public HermesVoice origin as the app's configurable backend base URL.

Expected current origin from project planning: `https://hermes-voice.dashanddata.com`

If the human gives a different hostname, verify it before changing code. The app should not hard-code a separate API host unless the project docs say so. Prefer one public origin with path-based routes.

## API and WebSocket expectations

Use HTTPS for normal API/auth calls.

Derive the voice WebSocket from the same origin using secure WebSocket, for example:

- HTTPS origin: `https://hermes-voice.dashanddata.com`
- WebSocket origin: `wss://hermes-voice.dashanddata.com`
- Public voice WebSocket path: `/ws/voice`

Do not assume localhost, `127.0.0.1`, LAN IPs, or a local FastAPI process for mobile app integration testing.

## Auth expectations

Use the existing end-user auth flow. Prefer email/password/2FA/session behavior that matches the web app.

Do not embed bearer tokens, API keys, `.env` secrets, or production credentials in the mobile app bundle or committed source.

If the current backend exposes a temporary API-key fallback for WebSocket development, treat it as a dev bridge only and document it clearly. Do not ship a mobile client that depends on an embedded secret.

## When a local Python backend is not needed

A local backend is not required for:

- Building mobile screens
- Implementing login UI against the public service
- Testing session establishment
- Testing WebSocket connection and reconnect behavior
- Testing push-to-talk / microphone capture against the real voice pipeline
- Testing real end-to-end HermesVoice behavior

For this experimental phase, treating the only running HermesVoice instance as both dev and production is acceptable.

## When a local Python backend is needed

Only require a local backend if you are:

- Changing backend API contracts
- Adding or modifying backend routes
- Changing auth/session semantics
- Changing the WebSocket protocol
- Writing or running backend pytest tests
- Debugging server-side errors that cannot be diagnosed from the public instance logs
- Needing mocked provider behavior that the public backend cannot provide

If you believe local backend setup is necessary, stop and report exactly which backend contract or server-side behavior blocks the mobile work.

## Implementation guidance

Make the backend origin configurable by build flavor, environment file, or runtime developer setting. Do not scatter the URL through the codebase.

Keep mobile behavior aligned with the existing web app where possible:

- Same public origin
- Same auth assumptions
- Same `/ws/voice` path
- Same user-visible connection states where practical
- Manual reconnect/check controls are acceptable for mobile browser/native instability

Add a short developer note explaining how to point the mobile app at the public backend.

## Testing checklist

Before declaring the mobile integration done, verify:

- The app builds on the Mac dev environment.
- The configured backend URL is not localhost.
- Login/auth flow reaches the public backend.
- The app can open the secure voice WebSocket at `/ws/voice`.
- Push-to-talk records non-empty audio and sends realistic audio payloads, not tiny header-only blobs.
- The app handles disconnect/reconnect visibly.
- No secrets or `.env` files were read, printed, committed, or embedded.

## Report back

When finished, report:

- The configured public backend origin used
- Files changed
- Tests/build commands run
- Whether auth was tested manually
- Whether WebSocket voice was tested manually
- Any backend-side blocker, if one actually exists
