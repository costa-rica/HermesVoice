# TODO — HermesVoice iOS Mobile via sherpa-onnx Adaptation

Date: 2026-04-30 (America/Los_Angeles)
Branch: `dev_04_new_mobile`
Scope: build a native Swift/SwiftUI iOS client at `mobile/ios/HermesVoice/...`
by **cloning and adapting** the sherpa-onnx Swift VAD example, then layering
HermesVoice auth, WebSocket protocol, and TTS playback on top. The backend at
`https://hermes-voice.dashanddata.com` is the only target — no local Python
backend is to be set up unless explicitly required by a phase.

Source documents:

- `docs/20260430_INTEGRATE_OS_MOBILE_ASSESSEMENT.md` (this TODO implements it)
- `docs/20260430hermesvoice-mobile-vad-research.md` (research basis)
- `docs/20260430 Mobile App Public Backend Agent Instructions.md` (backend rules)
- `docs/PROTOCOL.md` (WebSocket wire contract)
- `docs/archived/20260430_HERMES_VOICE_PLAN_V06_MOBILE.md` (preserved auth/state mandates)
- `docs/LOGGING_PYTHON_V06.md`, `docs/ERROR_REQUIREMENTS.md`

This TODO follows `docs/TODO_LIST_GUIDANCE.md`: phases are discrete, testable
units. After each phase, run the relevant checks, check off only items that
pass, then commit referencing this file and the phase.

---

## Architecture mandate (do not drift)

- **Native Swift/SwiftUI, iOS 17+.** No React Native, no Flutter.
- **One third-party dependency: sherpa-onnx iOS xcframework** (pinned release).
  Used solely for on-device VAD via the bundled Silero VAD ONNX model. The
  on-device ASR / TTS / decoder paths from sherpa-onnx are **not** used.
- **Single public origin.** All traffic to `https://hermes-voice.dashanddata.com`
  (HTTPS) and `wss://hermes-voice.dashanddata.com/ws/voice` (WSS).
- **End-user auth.** Email + password + emailed 2FA via `/api/auth/*`. No
  embedded bearer tokens, API keys, or `.env` secrets in shipped builds.
- **Configurable origin.** The base URL is set via a build config / Settings
  override, not hardcoded across files.
- **No local backend.** Do not stand up the Python API on this Mac. If a
  backend contract appears missing, stop and report — do not work around it.
- **Vendored, not forked.** Copy the relevant sherpa-onnx Swift example files
  into the HermesVoice repo; do not git-submodule the sherpa-onnx repo.
- **Web client untouched.** No changes outside `mobile/`, except the noted
  config docs.

## Critical caveats

- **Phase 0 gates everything.** If the sherpa-onnx VAD demo cannot be made to
  fire speech-start / speech-end on a physical iPhone, abort and reassess.
- **Phase 3 verifies backend contract.** Before writing client protocol code,
  confirm `client_hello` negotiation and `/api/auth/*` endpoints are live on
  the deployed backend. If either is missing, stop and report.
- **Vendored sherpa-onnx code is pinned.** Record the upstream commit / release
  tag in `mobile/ios/HermesVoice/Vendor/sherpa-onnx/UPSTREAM.md`.
- **No Opus path.** Default downlink is `aac_adts`; mandatory fallback is
  `wav_pcm16`. No `libopus` SPM dependency is added.

---

## Phase 0 — Validate sherpa-onnx VAD demo on physical iPhone

Goal: prove the foundation works before any HermesVoice code is written.

- [ ] Identify the latest sherpa-onnx iOS release at
      https://github.com/k2-fsa/sherpa-onnx/releases — record the tag.
- [ ] Download the iOS xcframework binary release.
- [ ] Clone the sherpa-onnx repo and locate the Swift VAD example
      (`swift-api-examples/` — the streaming-microphone VAD target, or the
      nearest equivalent in the chosen release).
- [ ] Build the example in Xcode against the downloaded xcframework.
- [ ] Run the example on a physical iPhone (not Simulator). Confirm:
  - VAD speech-start fires when speaking
  - VAD speech-end fires within ~1s of silence
  - No crashes after 5 minutes of mixed speech / silence
- [ ] Record observations in
      `docs/audio_spike/20260430_sherpa_onnx_vad_spike.md`: chosen release,
      Silero model path, observed sensitivity, any quirks.

Checks: example builds; VAD callbacks verified on device; spike note written.

Commit: `chore(mobile): validate sherpa-onnx iOS VAD demo on device`.

---

## Phase 1 — Project scaffold and vendored VAD harness

Goal: stand up `mobile/ios/HermesVoice/` with the sherpa-onnx VAD harness
copied in and wired to a minimal SwiftUI screen that displays VAD events.

- [ ] Create directory `mobile/ios/HermesVoice/` with an Xcode project named
      `HermesVoice.xcodeproj`. iOS 17+ deployment target. SwiftUI lifecycle.
- [ ] Add the sherpa-onnx xcframework under
      `mobile/ios/HermesVoice/Vendor/sherpa-onnx/` and link it into the app
      target (Embed & Sign).
- [ ] Bundle the Silero VAD ONNX model file into the app's Resources.
- [ ] Copy the Swift VAD example files (the AVAudioEngine tap + `SherpaOnnxVad`
      wrapper) into `mobile/ios/HermesVoice/Vendor/sherpa-onnx-swift/`. Strip
      ASR / decoder / TTS code paths — keep only VAD + audio capture.
- [ ] Write `mobile/ios/HermesVoice/Vendor/sherpa-onnx/UPSTREAM.md` recording
      the upstream release tag, what files were copied, and what was removed.
- [ ] Implement `VoiceActivityDetector.swift` as a Swift actor wrapping the
      vendored VAD with a clean `AsyncStream<VADEvent>` API.
- [ ] Build a minimal SwiftUI screen `VADTestView.swift` that shows live
      "speaking" / "silent" state from the actor.
- [ ] Configure Background Audio capability in `Info.plist` (UIBackgroundModes
      includes `audio`); set `AVAudioSession` category to `.playAndRecord` with
      `.mixWithOthers` and `.defaultToSpeaker`.
- [ ] Confirm on-device: VAD continues firing with the screen off and the app
      backgrounded.

Checks: Xcode build succeeds; app runs on device; VAD events show in UI;
background-audio behavior verified by lock-screen test.

Commit: `feat(mobile): scaffold iOS app with vendored sherpa-onnx VAD harness`.

---

## Phase 2 — Configurable backend origin

Goal: ensure the public origin is set in one place and overridable in dev.

- [ ] Create `mobile/ios/HermesVoice/Config/AppConfig.swift` exposing
      `baseURL` (HTTPS) and `voiceWebSocketURL` (WSS) derived from the same
      origin string.
- [ ] Default origin: `https://hermes-voice.dashanddata.com`.
- [ ] Allow override via a Settings bundle entry `HermesVoice.backendOrigin`
      (read at app launch). Document in `mobile/ios/README.md`.
- [ ] Assert at launch that the configured origin is HTTPS and not localhost
      / 127.0.0.1 / a LAN IP — log an error and refuse to start the voice
      flow if so.
- [ ] Add a tiny `mobile/ios/README.md` explaining how to change the origin
      and how to point the simulator at a staging URL if needed.

Checks: app launches with default origin; toggling Settings override changes
the URL used by a debug log line; non-HTTPS origin triggers refusal.

Commit: `feat(mobile): configurable backend origin with HTTPS guardrail`.

---

## Phase 3 — Verify backend contract is live (no code yet)

Goal: confirm the deployed backend supports what later phases require, before
writing client code against it.

- [ ] Using `curl` (no client code), verify the deployed backend responds at:
  - `GET https://hermes-voice.dashanddata.com/api/auth/session` → 401 or 200
  - `POST https://hermes-voice.dashanddata.com/api/auth/login` → known shape
  - `POST https://hermes-voice.dashanddata.com/api/auth/verify` → known shape
  - `POST https://hermes-voice.dashanddata.com/api/auth/logout` → known shape
- [ ] Using a CLI WebSocket tool (e.g. `websocat`) with a developer bearer or
      cookie, open `wss://hermes-voice.dashanddata.com/ws/voice` and send a
      `client_hello` per `docs/PROTOCOL.md`. Verify the server returns
      `session_started` with a `downlink_format` field.
- [ ] Record findings in `docs/audio_spike/20260430_backend_contract_check.md`.
- [ ] If any endpoint or `client_hello` handling is missing on the live
      backend: **STOP**. Do not proceed. Report which contract is missing so
      the backend can be updated on avatar08.

Checks: contract-check note exists and shows all four auth endpoints + WS
negotiation working against the live origin.

Commit: `docs(mobile): verify live backend contract for iOS integration`.

---

## Phase 4 — Auth flow against live backend

Goal: end-user can log in and the session persists.

- [ ] Implement `AuthService.swift` using `URLSession` with a shared
      `HTTPCookieStorage` for the `hv_session` cookie:
  - `login(email, password) async throws -> LoginResult` (returns a
    "needs 2FA" indicator with any session handle the backend provides)
  - `verify(code) async throws -> Session`
  - `logout() async throws`
  - `restoreSession() async throws -> Session?` calling `/api/auth/session`
- [ ] Persist the `hv_session` cookie via Keychain (not UserDefaults).
- [ ] Implement SwiftUI screens:
  - `LoginView` (email + password)
  - `TwoFactorView` (6-digit code input)
  - `LoadingView` shown while `restoreSession()` runs at launch
- [ ] Implement `AppRootView` that routes between unauthenticated and
      authenticated states based on `AuthService` state.
- [ ] Surface auth errors using `docs/ERROR_REQUIREMENTS.md` patterns: typed
      `AuthError`, user-visible message, no PII in logs.
- [ ] Manual test against the live backend with a real account: login →
      2FA → restored session on relaunch → logout.

Checks: build succeeds; unit tests for `AuthService` parsing pass; manual
E2E auth flow works against `hermes-voice.dashanddata.com`.

Commit: `feat(mobile): auth flow against live HermesVoice backend`.

---

## Phase 5 — WebSocket protocol scaffolding

Goal: typed frames and a connected socket — no audio yet.

- [ ] Implement `VoiceProtocol.swift` with Codable types per `docs/PROTOCOL.md`:
  - Outbound: `ClientHello`, `StartUtterance`, `EndOfUtterance`, `CancelTurn`,
    `Ping`
  - Inbound: `SessionStarted`, `TurnStarted`, `Transcript`, `AssistantText`,
    `ActiveState`, `AudioChunk` (prelude), `TurnEnd`, `VoiceTurnSkipped`,
    `ThinkingProgress`, `ErrorFrame`, `Pong`
- [ ] Implement `VoiceSocket.swift` over `URLSessionWebSocketTask`:
  - Connect to `AppConfig.voiceWebSocketURL` carrying the auth cookie
  - Send `client_hello` with
    `accepted_downlink_formats: ["aac_adts", "wav_pcm16"]` on open
  - Track state machine with a pending-binary slot driven by `audio_chunk`
    preludes; reject orphan binary frames as protocol errors
  - Track current `turn_id` for stale-frame filtering
  - Reject unknown JSON frames safely (log and ignore)
  - Expose an `AsyncStream<InboundEvent>` to consumers
- [ ] Implement reconnect with exponential backoff (1s → 2s → 4s → 8s, cap 30s)
      on unexpected close. On auth-failure close codes, route back to login.
- [ ] Unit-test the protocol decoder against canned frames including the
      `audio_chunk` prelude → binary pairing and stale-turn filtering.
- [ ] Manual test: app connects, receives `session_started`, displays the
      negotiated `downlink_format` in a debug HUD.

Checks: unit tests pass; `xcodebuild test` green; manual connection succeeds
against live backend.

Commit: `feat(mobile): WebSocket protocol with turn-aware framing`.

---

## Phase 6 — Uplink: VAD → WebSocket audio streaming

Goal: speak into the device, backend receives a complete utterance.

- [ ] Implement `AudioUplink.swift` connecting `VoiceActivityDetector` events
      to `VoiceSocket`:
  - On `speech_start`: send `start_utterance`; begin tapping mic PCM at
    16 kHz / 16-bit / mono into 20 ms binary frames sent over WS
  - On `speech_end`: flush remaining buffer; send `end_of_utterance`
  - Prepend a small lookback (~300 ms) so the start of speech isn't clipped
- [ ] Coalesce VAD jitter: ignore speech_end if a new speech_start fires
      within ~150 ms (configurable).
- [ ] Reject empty utterances (< 200 ms of speech) without sending — purely
      a client-side guardrail.
- [ ] Manual on-device test: speak a short phrase; observe the backend
      respond with a `transcript` and `assistant_text` JSON frame.
- [ ] Verify uplink works with screen off (continuation of Phase 1).

Checks: build green; unit tests for the VAD-jitter coalescer pass; manual
E2E uplink results in a non-empty transcript from the backend.

Commit: `feat(mobile): VAD-driven audio uplink to /ws/voice`.

---

## Phase 7 — Downlink: TTS playback with turn-keyed queue

Goal: app speaks Hermes responses; cancellation works cleanly.

- [ ] Implement `AudioPlayer.swift` using `AVAudioEngine` +
      `AVAudioPlayerNode`. Decode paths:
  - `aac_adts`: feed each chunk through `AVAudioConverter` into
    `AVAudioPCMBuffer` and schedule on the player node
  - `wav_pcm16`: wrap raw PCM bytes directly in `AVAudioPCMBuffer` and
    schedule on the player node
- [ ] On `audio_chunk` prelude: stash `turn_id`, `format`, `seq`, `bytes`;
      pair with the next binary frame.
- [ ] On binary frame: if its prelude `turn_id` ≠ current active turn, drop
      it (stale-audio filtering per `docs/PROTOCOL.md` Option A).
- [ ] On `turn_end`: drain the player queue; transition state machine.
- [ ] Implement Cancel control: on user cancel, call `playerNode.stop()` +
      `playerNode.reset()`, send `cancel_turn` with the active `turn_id`,
      then drop subsequent frames whose `turn_id` matches the canceled turn.
- [ ] Handle decoder-state reset cleanly between turns (no clicks, no
      trailing audio from the previous turn).
- [ ] Manual on-device tests:
  - Two back-to-back turns, no audio bleed
  - Cancel during `thinking` — no TTS plays
  - Cancel during `speaking` — TTS stops within ~200 ms

Checks: build green; manual playback + cancel scenarios verified on device.

Commit: `feat(mobile): TTS downlink playback with turn-keyed cancellation`.

---

## Phase 8 — State machine, multi-turn loop, connection UX

Goal: hands-free continuous conversation with visible connection states.

- [ ] Implement `ConversationState.swift` mirroring the V04 `active_state`
      values 1:1: `idle`, `listening`, `thinking`, `thinking_progress`,
      `speaking`, `awaiting_approval`, `reconnecting`.
- [ ] Drive UI from this state:
  - SwiftUI `ConversationView` showing current state, last transcript, and
    last assistant text
  - Visual indicator (waveform / dot color) for `listening` vs `speaking`
- [ ] Multi-turn auto-resume: when the player queue drains and the server
      sends `turn_end` + `active_state=idle`, automatically re-arm VAD.
- [ ] Manual reconnect button visible whenever the socket is closed or
      reconnecting.
- [ ] Handle `AVAudioSessionInterruptionNotification` (phone call, Siri):
      pause VAD, route to `idle`; resume on `.ended` with
      `.shouldResume` option.
- [ ] Manual on-device test: 3+ consecutive turns hands-free, screen off
      during at least one turn.

Checks: build green; multi-turn E2E test passes; interruption + resume
behaves correctly.

Commit: `feat(mobile): hands-free multi-turn loop with connection UX`.

---

## Phase 9 — Hardening, logging, and TestFlight build

Goal: shippable build with logs that aid debugging without leaking PII.

- [ ] Audit the bundle: no `.env`, no API keys, no embedded bearer tokens.
      Add a Run Script build phase that fails the build if any of those
      patterns appear in the bundle.
- [ ] Verify configured origin is not localhost / LAN IP in any non-debug
      build configuration.
- [ ] Add `os.Logger` instrumentation per `docs/LOGGING_PYTHON_V06.md` spirit
      (levels, structured fields, no PII): connection lifecycle, VAD
      transitions, turn lifecycle, errors.
- [ ] Implement user-visible error surfacing per
      `docs/ERROR_REQUIREMENTS.md`: typed errors, friendly copy, retry
      affordances where appropriate.
- [ ] Run Xcode "Analyze" pass; resolve any warnings.
- [ ] Confirm app icon, launch screen, display name, bundle ID are set.
- [ ] Archive a Release build → upload to TestFlight.
- [ ] Smoke-test the TestFlight build on a physical iPhone:
  - Login + 2FA
  - One full hands-free conversation, 3+ turns
  - Cancel mid-turn
  - Background → foreground → conversation resumes

Checks: Release archive succeeds; TestFlight smoke test passes.

Commit: `feat(mobile): hardening, logging, and TestFlight readiness`.

---

## Done criteria

- The app at `mobile/ios/HermesVoice/` builds cleanly in Xcode (Debug + Release).
- Hands-free continuous voice conversation works against
  `https://hermes-voice.dashanddata.com` on a physical iPhone, including with
  the screen off.
- No `.env` files, API keys, or bearer tokens are in the bundle or committed.
- The backend on avatar08 was not reconstructed locally at any point.
- The vendored sherpa-onnx code is clearly isolated under `Vendor/` with a
  pinned upstream tag recorded in `UPSTREAM.md`.
