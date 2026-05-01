# HermesVoice — Plan V05 (Native iOS Mobile)

**Date:** 2026-04-30 (America/Los_Angeles)
**Supersedes (mobile sections only):** `docs/20260428_HERMES_VOICE_PLAN_V04.md` § "Mobile App"
**Companion plan:** V04 remains authoritative for backend, web, and deployment.
**Scope:** Native Swift/SwiftUI iOS app for HermesVoice.

V05 narrows the mobile plan to a concrete native iOS implementation that
replicates the core product behavior of the existing web app — push-to-talk
voice conversation with Hermes — while choosing iOS-native primitives over
browser-specific implementation details. It also fixes the host model: the
mobile app talks to the same public origin as the web app, with path-based
routes, and uses end-user authentication rather than an embedded bearer key.

---

## What changed since V04

- **Single public host, path-based routing.** The mobile app communicates with
  `https://hermes-voice.dashanddata.com` using path-based endpoints on the same
  origin. It does **not** use a separate API hostname such as
  `api.hermes-voice.dashanddata.com`. The deployed FastAPI service serves both
  the marketing/site response at `/` and the API/WebSocket surfaces (`/ws/voice`,
  `/health/live`, `/health/ready`, `/login`, `/login/verify`, `/logout`) on the
  same origin behind the same TLS cert.
- **`/` may render the site.** Returning HTML from `/` is allowed — the site
  and the API share the host. API surfaces remain at well-known paths
  (`/ws/voice`, `/health/*`, `/login*`, `/api/*` if introduced) and are not
  affected by what `/` chooses to serve.
- **End-user auth for the shipped iOS app.** The shipped iOS binary
  authenticates the human user with permitted email + password + emailed 2FA
  code, then carries a server-issued session credential. The bearer
  `HERMES_VOICE_API_KEY` is **not** embedded in the App Store / TestFlight
  binary. Bearer-key auth remains supported by the backend and is appropriate
  for internal scripts, dev builds, and service-to-service callers.
- **Native iOS primitives over browser shims.** `URLSessionWebSocketTask`,
  `AVAudioEngine`/`AVAudioRecorder`, `AVAudioSession`, and `AVAudioPlayer` /
  `AVAudioEngine` replace `MediaRecorder`, `AudioContext`, and the browser
  fetch/cookie path used by `web/`.

V05 leaves V04 untouched for backend, web, chunking, WebSocket framing, and
deployment topology except for the host-model clarification above. Where any
older doc (including the V02 TODO) references
`api.hermes-voice.dashanddata.com`, treat it as superseded for the mobile
client.

---

## Host model and URL derivation

### Single-origin assumption

The existing FastAPI service on `avatar08:8700`, fronted by `maestro04` Nginx,
already terminates one TLS cert for `hermes-voice.dashanddata.com` and serves:

- `/` — site/marketing or web app shell (HTML).
- `/login`, `/login/verify`, `/logout` — interactive web auth (HTML/forms).
- `/api/*` — JSON endpoints (existing or new mobile-facing endpoints).
- `/ws/voice` — WebSocket voice contract (`wss://`).
- `/health/live`, `/health/ready` — operator health probes.

The mobile app must treat this single origin as both website and API. Nginx
already includes a dedicated `location /ws/` upgrade block before the generic
`location /` (per V04 § Reverse-proxy deployment), so WebSocket and HTTP
share the host without conflict.

### URL configuration in the iOS app

The Swift app derives all URLs from one configurable string,
`apiOrigin`, defaulting to `https://hermes-voice.dashanddata.com`:

| Purpose | Derivation |
|---|---|
| API base | `apiOrigin` (HTTPS) |
| Login / verify | `\(apiOrigin)/login`, `\(apiOrigin)/login/verify` |
| Logout | `\(apiOrigin)/logout` |
| Mobile auth (if added) | `\(apiOrigin)/api/auth/...` (see below) |
| Health (debug only) | `\(apiOrigin)/health/ready` |
| WebSocket | replace scheme: `https://` → `wss://`, append `/ws/voice` |

Configuration sources, in priority order:

1. In-app **Settings** screen (developer/diagnostic override, persisted in
   `UserDefaults` under `HermesVoice.apiOrigin`).
2. Build-time `Info.plist` value `HermesVoiceAPIOrigin` baked per scheme
   (Debug/Release).
3. Hard-coded fallback constant `https://hermes-voice.dashanddata.com`.

The app must reject non-HTTPS origins in Release builds (no plaintext HTTP
override, no ATS exceptions). Debug builds may permit `http://localhost:8700`
behind a build flag for local backend testing on the Mac/Simulator.

### What the app never embeds

- `HERMES_VOICE_API_KEY` — server bearer token. Only ever lives in
  `api/.env` on `avatar08`, in a developer's Mac keychain for scripts, or in
  a private internal build that is not distributed.
- `OPENAI_API_KEY`, `HERMES_API_KEY`, `SESSION_SECRET`, `HERMES_VOICE_WEB_PASSWORD`.

---

## Authentication for end users

### Why not a bearer key in the shipped app

A shipped iOS binary is extractable. Embedding a long-lived bearer that grants
access to the OpenAI-backed pipeline (paid Whisper + TTS + Hermes) is a leak
risk and provides no per-user accountability. End users authenticate as
themselves; the backend remains the only holder of provider credentials.

### Mobile login flow (V1)

The mobile app reuses the existing two-factor flow already implemented for the
web app (allowed-email + `HERMES_VOICE_WEB_PASSWORD` + emailed numeric code),
exposed as JSON endpoints suitable for a native client. Either:

- **Option A — JSON wrappers around the existing routes** (recommended).
  Add `/api/auth/login`, `/api/auth/verify`, `/api/auth/logout`,
  `/api/auth/session` that accept and return JSON, share the existing email
  allow-list, password check, code issuance, rate limiter, and lockout, and
  set the same `hv_session` cookie as the web flow.
- **Option B — reuse `/login` and `/login/verify`** as-is by submitting form
  data from the iOS app. Acceptable but couples the mobile client to HTML
  form semantics; prefer Option A.

Either way, the mobile flow is:

1. User enters email + password on a SwiftUI login screen.
2. `POST /api/auth/login` — backend validates, throttles, and emails a
   one-time code.
3. SwiftUI prompts for the 2FA code.
4. `POST /api/auth/verify` — backend validates the code and returns a session
   credential (see "Session credential" below).
5. App stores the credential in the iOS Keychain (`kSecClassGenericPassword`,
   `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`).
6. App transitions to the conversation screen and connects `wss://.../ws/voice`
   carrying the credential.

Logout calls `POST /api/auth/logout`, clears the Keychain entry, and tears
down the WebSocket.

### Session credential — cookie vs. token

`URLSessionWebSocketTask` honors `HTTPCookieStorage` for the underlying
upgrade request, so the cleanest path is:

- Backend continues to set the `hv_session` cookie (`HttpOnly`, `Secure`,
  `SameSite=Lax`, host-only on `hermes-voice.dashanddata.com`).
- iOS keeps cookies in a dedicated, persistent `HTTPCookieStorage`
  associated with a shared `URLSession` configuration. The same session is
  used for both REST calls and the WebSocket upgrade.
- The Keychain holds a small "logged-in" marker plus the email so the app can
  reattach the session after relaunch; the cookie itself can be persisted via
  `URLSession`'s shared cookie storage with `cookieAcceptPolicy = .always`.

If a token-based path is preferred for clarity on mobile, the backend may
additionally return a short-lived session token in the JSON body of
`/api/auth/verify`, which the app sends as `Authorization: Bearer <token>`
on REST calls and as a `Sec-WebSocket-Protocol` header or query parameter on the WS
upgrade. Pick **one** mechanism; do not ship both.

### 2FA mechanics

- Same 6-digit emailed code, same TTL, same allow-list, same per-IP and
  per-email throttles already built for `/login/verify`.
- Resend endpoint with its own throttle.
- Backend lockout policy and standardized error responses are unchanged.

### Bearer API key remains for internal/dev/service use

`HERMES_VOICE_API_KEY` continues to authenticate:

- Smoke scripts in `scripts/`.
- A developer's Xcode debug build that opts into header-based auth via a
  Settings toggle and a Keychain-stored key (never committed, never in plist).
- Future service-to-service automation.

The WebSocket endpoint must accept either cookie/session auth or
`Authorization: Bearer <HERMES_VOICE_API_KEY>` and continue to enforce
`Origin` checks for browser callers while permitting native-client requests
that omit `Origin` per WebSocket norms.

---

## Mapping web capabilities to native iOS

The native iOS app must reach behavioral parity with the V04 web client
before adding mobile-only features. Each web capability maps to a specific
iOS primitive:

### Push-to-talk capture

- **Web:** `MediaRecorder` over `getUserMedia`, typically producing
  `webm/opus`.
- **iOS:** `AVAudioEngine` input tap (or `AVAudioRecorder`) producing
  16 kHz / 16-bit / mono PCM, written to a WAV container in memory. This is
  the V04 "mobile V1 uplink" target.
- **PTT UI:** SwiftUI `Button` with `LongPressGesture(minimumDuration: 0)`
  starting capture on press, ending on release. Disabled until
  `session_started` arrives.
- **Permissions:** `NSMicrophoneUsageDescription` in `Info.plist`, request via
  `AVAudioApplication.requestRecordPermission` (iOS 17+) on first PTT press.

### Audio session

- `AVAudioSession` category `.playAndRecord`, mode `.voiceChat`, options
  `[.defaultToSpeaker, .allowBluetooth, .allowBluetoothA2DP]`.
- Activate before capture; deactivate with
  `notifyOthersOnDeactivation` after a turn completes if no playback is
  pending.
- Subscribe to `AVAudioSession.interruptionNotification` and
  `routeChangeNotification` to pause/resume cleanly during phone calls,
  Siri, and headset changes.

### Active states

The V04 contract emits `active_state` ∈ `{idle, listening, thinking,
thinking_progress, speaking, awaiting_approval}`. The Swift state machine is
a single `enum ActiveState` mirrored 1:1; the SwiftUI view model exposes it
as `@Published` and the screen renders:

| State | iOS rendering |
|---|---|
| `idle` | PTT button enabled, "Hold to talk" label |
| `listening` | Recording indicator, mic level meter |
| `thinking` | Spinner + "Hermes is thinking…" |
| `thinking_progress` | Same spinner + non-error progress text |
| `speaking` | Waveform animation while audio plays |
| `awaiting_approval` | Distinct banner + "Approve / Deny" affordance if/when the backend exposes it; otherwise non-interactive status text and a Cancel button |

`awaiting_approval` is rendered as a recognized, non-error state. When the
backend's tool-approval contract lands, the same SwiftUI surface gains the
approve/deny actions.

### Transcript and assistant text

- `transcript` JSON frames → user chat bubble (right-aligned).
- `assistant_text` JSON frames → Hermes chat bubble (left-aligned), final
  text only.
- `voice_turn_skipped` with `reason="audio_too_short"` → inline toast: "Hold
  longer to record" and return to idle.
- Unknown JSON frames are logged at debug and ignored.

### Streamed audio playback

- **Web:** `AudioContext` queue decoding Opus chunks.
- **iOS:** `AVAudioEngine` with an `AVAudioPlayerNode` and a serial queue of
  `AVAudioPCMBuffer`s, or a streaming `AVAudioPlayer` chain keyed by the
  current turn id. Concrete approach:
  - Each binary WS frame is an Opus chunk (per V04 `DOWNLINK_FORMAT=opus`).
  - Decode with `AVAudioConverter` into PCM buffers.
  - Schedule onto `AVAudioPlayerNode` in arrival order.
  - Tag each scheduled buffer with the active `turnId`.

### Cancel / interruption

The iOS Cancel control must:

1. **Stop local playback immediately.** Call `playerNode.stop()` and
   `playerNode.reset()` to flush all queued buffers — without this, queued
   PCM continues playing after the user taps Cancel.
2. Drop any binary frames received after the cancel that carry the now-stale
   `turnId`.
3. Send `{"event":"cancel_turn"}` over the WebSocket.
4. Optimistically transition `ActiveState` to `idle`.
5. Accept the backend's `active_state=idle` and `turn_end` confirmation.

The same flow applies during `thinking`, `thinking_progress`, `speaking`,
and any active assistant playback. Cancel during `listening` simply stops
capture without sending audio.

### Connection lifecycle: Ready / Checking / Offline

The web app exposes Ready, Checking, and Offline indicators with manual
check/reconnect. iOS replicates:

- **Ready:** WebSocket open, `session_started` received with
  `conversation_id`. PTT enabled.
- **Checking:** Manual reconnect tapped, or app foregrounded after >N
  seconds in background, or no `pong` within timeout. Send `{"event":"ping"}`
  and require a matching `pong` within 5 seconds; on timeout, force
  reconnect.
- **Offline:** Socket closed or upgrade refused. Show "Tap to reconnect."
  PTT disabled.

Implementation notes:

- Use `URLSessionWebSocketTask` with `pingHandler` for keepalive (separate
  from the application-level `ping`/`pong` frames).
- Listen to `NWPathMonitor` for OS-level reachability. Treat OS "no path" as
  Offline immediately rather than waiting for socket failure.
- On `ScenePhase` transitions to `.active`, send an application-level ping
  rather than tearing down on every foregrounding (avoid false reconnect
  loops from background timer throttling).
- Reconnection always starts a new session in V1; no resume promise.

### `session_started` and conversation lifecycle

- App connects → backend mints `conversation_id` → emits
  `{"event":"session_started","conversation_id":"<uuid>"}`.
- Swift view model stores `conversationId`, transitions `ActiveState` to
  `idle`, enables PTT.
- A user-initiated "New conversation" action sends
  `{"event":"new_session"}`; the backend cancels any active turn, mints a
  new id, and emits a fresh `session_started`. The UI clears the transcript
  on receipt of the new `session_started`, not on the local tap, so the
  visible conversation always matches the server's notion.
- Disconnect cancels the active turn server-side. The app does not promise
  resume.

### Errors

- `error` JSON frames with `{code, message, status}` are rendered as a
  dismissible banner. Connection-level errors transition to Offline rather
  than crashing the screen. Standardized error shapes from
  `docs/ERROR_REQUIREMENTS.md` are mirrored as a Swift `struct ServerError`.

---

## Backend / public deployment changes to support the mobile client

The backend is largely ready. The following items are needed or tightened
for V05:

### Required additions

1. **JSON auth endpoints.** Add `/api/auth/login`, `/api/auth/verify`,
   `/api/auth/logout`, `/api/auth/session` mirroring the existing web login
   semantics. Reuse the existing rate limiter, lockout, allow-list, and
   email-code issuer. Set the same `hv_session` cookie on success.
2. **Cookie scope review.** Because the web and mobile clients now share
   one host, the cookie can be host-only on
   `hermes-voice.dashanddata.com`. Remove any cross-subdomain
   `Domain=.dashanddata.com` setting if present from the V02 two-host
   design.
3. **CORS.** With single-origin, CORS is unnecessary for the mobile app
   (native clients ignore CORS) and unnecessary for the web app (same
   origin). Keep CORS off in production except for explicit dev origins.
4. **WebSocket auth acceptance.** Confirm `/ws/voice` accepts (a) the
   `hv_session` cookie carried by the WS upgrade, and (b)
   `Authorization: Bearer <HERMES_VOICE_API_KEY>` for internal callers.
   Continue to validate `Origin` only when present.
5. **Server-side cancel_turn handling.** V04 already documents
   `cancel_turn`; verify the implementation cancels the active task without
   tearing down the socket or session.
6. **`awaiting_approval` contract.** Document the inbound shape the client
   should send to approve/deny when this lands; keep the state name stable
   so the iOS rendering does not churn.

### Operational

- TLS already covers `hermes-voice.dashanddata.com`. No second cert needed.
- Nginx `/ws/` upgrade block already in place (per V04).
- App Transport Security: production origin uses TLS 1.2+ with a public CA
  cert via Certbot — meets ATS defaults; no `Info.plist` exceptions
  required for Release.
- Rate limits should treat mobile login traffic the same as web; consider
  adding a per-device-id soft limit later if abuse appears.

### Things explicitly **not** changing

- Hermes stays loopback-only on `127.0.0.1:8642`.
- TTS chunking heuristic, `start_utterance` framing, idle timeouts,
  `IDLE_TIMEOUT`, `MAX_UTTERANCE_BYTES`, and the binary/JSON frame contract
  are unchanged.
- Web client behavior is unchanged.

---

## iOS app structure

```
mobile/ios/HermesVoice/
├── HermesVoice.xcodeproj
├── HermesVoice/
│   ├── HermesVoiceApp.swift         # @main, ScenePhase wiring
│   ├── Config/
│   │   ├── AppConfig.swift          # apiOrigin, build flags, URL derivation
│   │   └── Info.plist               # mic usage description, ATS defaults
│   ├── Auth/
│   │   ├── AuthClient.swift         # /api/auth/* JSON calls
│   │   ├── SessionStore.swift       # Keychain + cookie persistence
│   │   └── LoginView.swift          # SwiftUI email + password + 2FA
│   ├── Voice/
│   │   ├── VoiceSocket.swift        # URLSessionWebSocketTask wrapper
│   │   ├── VoiceProtocol.swift      # Codable frames, ActiveState enum
│   │   ├── AudioCapture.swift       # AVAudioEngine PTT → WAV bytes
│   │   ├── AudioPlayback.swift      # AVAudioEngine queue + cancel reset
│   │   ├── AudioSessionManager.swift# AVAudioSession config + interruptions
│   │   └── ConversationViewModel.swift
│   ├── UI/
│   │   ├── ConversationView.swift   # PTT, transcript, status, cancel
│   │   ├── ConnectionStatusView.swift # Ready / Checking / Offline
│   │   └── SettingsView.swift       # apiOrigin override, logout, debug
│   └── Diagnostics/
│       └── Logger.swift
└── HermesVoiceTests/
    ├── VoiceProtocolTests.swift
    ├── ConversationStateTests.swift
    └── AudioCaptureTests.swift
```

Build target: iOS 17.0+. SwiftUI for views, async/await throughout, no
third-party SDKs in V1.

---

## Phased delivery (mobile only)

Phase numbers continue from V04. All Xcode work is on Nick's MacBook Air;
Ubuntu only edits Swift/docs.

### M0 — Backend prep on Ubuntu (no Xcode required)
- [ ] Add `/api/auth/login`, `/api/auth/verify`, `/api/auth/logout`,
      `/api/auth/session` JSON endpoints reusing existing web-auth internals.
- [ ] Confirm `hv_session` cookie is host-only on
      `hermes-voice.dashanddata.com`.
- [ ] Confirm `/ws/voice` accepts both cookie and bearer auth.
- [ ] Add backend tests for the JSON auth endpoints (rate limit, lockout,
      bad code, expired code, success path, logout).

### M1 — Xcode project skeleton (Mac)
- [ ] Create `mobile/ios/HermesVoice/` Xcode project, iOS 17 target.
- [ ] Add `AppConfig` with `apiOrigin` resolution order and HTTPS guard.
- [ ] Add SwiftUI shell with placeholder Login and Conversation screens.

### M2 — Auth (Mac)
- [ ] Implement `AuthClient` against `/api/auth/*`.
- [ ] Implement `SessionStore` (Keychain marker + persistent cookie storage).
- [ ] Build the email + password + 2FA SwiftUI flow.
- [ ] Logout clears Keychain and cookies.

### M3 — WebSocket and protocol (Mac)
- [ ] Implement `VoiceProtocol` Codable frames and `ActiveState` enum.
- [ ] Implement `VoiceSocket` over `URLSessionWebSocketTask` carrying the
      session cookie on upgrade.
- [ ] Render `session_started`, `transcript`, `assistant_text`,
      `active_state`, `turn_end`, `voice_turn_skipped`, `error`, `pong`.
- [ ] Ignore unknown JSON frames safely.

### M4 — Audio capture and uplink (Mac + iPhone)
- [ ] Configure `AVAudioSession` for `.playAndRecord` / `.voiceChat`.
- [ ] Implement PTT capture → 16 kHz / 16-bit / mono WAV.
- [ ] Send `start_utterance` (`format="wav"`, `sample_rate=16000`), binary
      frames, then `end_of_utterance`.

### M5 — Audio playback and cancel (Mac + iPhone)
- [ ] Implement Opus → PCM decode and `AVAudioPlayerNode` queue.
- [ ] Cancel stops local playback immediately (`stop()` + `reset()`), drops
      stale-turn frames, sends `cancel_turn`.
- [ ] Validate end-to-end against the deployed backend.

### M6 — Connection UX (Mac + iPhone)
- [ ] Ready / Checking / Offline indicator + manual reconnect.
- [ ] `ping`/`pong` keepalive at the application level, with timeout-driven
      reconnect.
- [ ] `NWPathMonitor` integration for OS-level offline.
- [ ] `ScenePhase` rules that ping on resume rather than tearing down.

### M7 — Hardening (Mac + iPhone)
- [ ] Test interruptions: phone call, Siri, AirPods route changes.
- [ ] Test lock-screen playback continuity.
- [ ] Confirm mic permission UX, network permission UX, and ATS behavior in
      Release.
- [ ] Verify no secrets in the built `.ipa` via `strings`.

### M8 — TestFlight (Mac)
- [ ] Bundle id, signing team, provisioning profile, entitlements (Background
      Audio if used).
- [ ] Upload to TestFlight, internal test against the public backend.

---

## Open questions to resolve during M0–M3

- Should `/api/auth/verify` additionally return a JSON session token alongside
  the cookie, or stay cookie-only? (Default: cookie-only.)
- Should the iOS app expose the developer bearer-key path in Settings, or keep
  it strictly compile-time in Debug? (Default: compile-time only.)
- Does `awaiting_approval` need an inbound `approve_turn` / `deny_turn`
  WebSocket event in V1, or can the iOS app render it as status-only until the
  approval product surface lands? (Default: status-only in V1.)

---

## Cross-references

- V04 plan: `docs/20260428_HERMES_VOICE_PLAN_V04.md` — backend, web, deployment.
- V02 TODO: `docs/requirements/20260428_TODO_HERMES_VOICE_V02.md` — Phase 8
  bullets are subsumed by M1–M8 above; the `api.hermes-voice.dashanddata.com`
  references in that document are superseded by the single-origin model here.
- Logging standard: `docs/LOGGING_PYTHON_V06.md`.
- Error standard: `docs/ERROR_REQUIREMENTS.md`.
