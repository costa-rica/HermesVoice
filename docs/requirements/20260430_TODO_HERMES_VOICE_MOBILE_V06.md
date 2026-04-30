# TODO — HermesVoice Native iOS Mobile (V06)

Date: 2026-04-30 (America/Los_Angeles)
Branch: `dev_03`
Scope: native Swift/SwiftUI iOS client at `mobile/ios/HermesVoice/...`, plus
backend wire-contract changes in `api/` required to unblock it. Web client is
out of scope and must remain unchanged.

Source documents:

- `docs/20260430_HERMES_VOICE_PLAN_V06_MOBILE.md` (authoritative)
- `docs/20260430_HERMES_VOICE_PLAN_V05_MOBILE.md` (superseded; preserved sections incorporated by reference from V06)
- `docs/20260430_HERMES_VOICE_PLAN_V05_MOBILE_ASSESSMENT_CODEX.md` (risk source)
- `docs/20260428_HERMES_VOICE_PLAN_V04.md` (backend/web baseline)
- `docs/LOGGING_PYTHON_V06.md`, `docs/ERROR_REQUIREMENTS.md`

This TODO follows `docs/TODO_LIST_GUIDANCE.md`: phases are discrete, testable
units; after each phase, run the relevant checks (backend `pytest`, web `npm
run build` if web-adjacent code is touched, Xcode build/tests once the iOS
target exists), check off completed items only after checks pass, then commit
with a message referencing this file and the phase.

---

## Architecture mandate (do not drift)

- **Native Swift/SwiftUI only.** No React Native, no Flutter, no third-party
  SDKs except the audio-decode carve-out below.
- **Single public origin.** All client traffic targets
  `https://hermes-voice.dashanddata.com`. No `api.` subdomain, no per-client
  hostnames.
- **End-user auth.** TestFlight / App Store builds authenticate humans via
  email + password + emailed numeric 2FA. The backend bearer
  `HERMES_VOICE_API_KEY` is **never** embedded in shipped builds; bearer is
  retained for internal scripts, dev builds, and service-to-service callers.
- **State machine** mirrors V04 `active_state` 1:1 (`idle → listening →
  thinking → speaking → idle`, plus `awaiting_approval`).
- **Audio decode carve-out.** Default mobile downlink is `aac_adts @ 24 kHz
  mono` decoded with built-in AVFoundation; mandatory fallback is `wav_pcm16
  @ 16 kHz mono` (zero-dependency). Opus is permitted only if M0a explicitly
  authorizes a `libopus`/`swift-opus` SPM dependency.
- **Web client unchanged in V06.** Do not force the web client into
  `client_hello` negotiation; preserve its existing implicit Opus path.

## Critical caveats

- **M0a (audio decode spike) gates M5.** No SwiftUI playback work commits to
  a specific decoder until the spike has produced audible speech end-to-end
  on a physical iPhone for the negotiated default format. If AAC fails on
  device, V1 ships `wav_pcm16` and AAC becomes a later optimization.
- **Cancellation correctness requires wire-contract changes.** Under V04
  framing, outbound binary frames carry no turn metadata, so client-side
  filtering of stale audio is unimplementable. Phase A1 must land before any
  M5 cancel logic is written.
- **Option A vs Option B is a one-time decision.** Phase A1 records the
  choice in `docs/PROTOCOL.md` (or equivalent contract doc). Once chosen, all
  downstream tests and client code follow that option; do not branch the
  client to support both.
- **Use the project Python.** `which python && python --version` before
  running any Python tooling (per `docs/TODO_LIST_GUIDANCE.md` Python rule).
  The known pytest venv path is
  `/home/limited_user/environments/hermes_voice/bin/pytest`.

## Acceptance criteria

The work in this TODO is complete when **all** of the following hold:

1. **Backend negotiation + new wire fields are live.** `/ws/voice` honors
   `client_hello`, returns the chosen `downlink_format` /
   `downlink_sample_rate` / `downlink_channels` in `session_started`,
   rejects unsatisfiable requests with a typed `unsupported_downlink`, and
   emits `turn_id` on every turn-scoped JSON frame. Covered by backend tests.
2. **Audio decode is proven on a physical iPhone.** M0a writeup exists at
   `docs/audio_spike/20260430_ios_downlink_spike.md` and records audible
   playback for the negotiated default format plus a clean back-to-back
   cancel.
3. **Cancellation is provably correct.** Backend tests confirm no further
   binary frames belong to the canceled turn after `cancel_turn` is acked,
   and iOS protocol tests (against a fake socket) confirm stale frames are
   never scheduled on the player under whichever Option (A or B) was chosen.
4. **End-to-end iOS turn works.** A signed-in TestFlight (or local-device)
   build can run at least three consecutive PTT turns against the deployed
   backend without re-handshake, with visible user/Hermes bubbles, a working
   active-state indicator, and a Cancel that produces no leaked audio.
5. **No bearer key in shipped builds.** Release configuration verified to
   contain no `HERMES_VOICE_API_KEY` literal; auth flows exclusively through
   `/api/auth/*` and the `hv_session` cookie.

---

## Phase A1 — Backend: wire-contract additions for negotiation + turn binding

Files likely touched:

- `api/app/ws/voice.py` (or wherever `/ws/voice` lives)
- `api/app/protocol/` or equivalent frame definitions
- `api/tests/test_ws_voice_*.py` (new + extended)
- `docs/PROTOCOL.md` (or equivalent contract doc) — record Option A vs B

Tasks:

- [x] Add `client_hello` handling on `/ws/voice` immediately after upgrade.
      Parse `accepted_downlink_formats`; pick the first server-supported
      format in client preference order.
- [x] Extend `session_started` with `downlink_format`, `downlink_sample_rate`,
      `downlink_channels`. Confirm web client still works (it does not send
      `client_hello`; server falls back to current implicit Opus path).
- [x] Close the socket with a typed `error` frame
      (`code="unsupported_downlink"`) when the intersection is empty.
- [x] Add `turn_id` to every turn-scoped JSON frame: `turn_started`,
      `active_state` (when not `idle`), `transcript`, `assistant_text`,
      `thinking_progress`, `voice_turn_skipped`,
      `turn_end`/`turn_completed`. Make it additive — do not remove or rename
      existing fields.
- [x] Accept optional `turn_id` on inbound `cancel_turn`; if absent, cancel
      the currently active turn. Echo the canceled `turn_id` in the
      resulting `turn_end`.
- [x] **Decision point:** choose Option A (per-chunk JSON `audio_chunk`
      prelude) or Option B (suppress-until-next-`turn_started`). Default per
      V06: Option A. Record the choice and rationale in
      `docs/PROTOCOL.md`.
- [x] Implement the chosen Option on the server side. For Option A, emit the
      JSON `audio_chunk` envelope immediately before each binary frame, with
      monotonic per-turn `seq` and exact `bytes` count. For Option B, ensure
      the outbound TTS queue is drained or discarded on cancel before any
      further binary frames are sent.

Tests:

- [x] `test_client_hello_negotiation_aac_default`: client offers all four
      formats; server picks `aac_adts`.
- [x] `test_client_hello_negotiation_pcm_fallback`: client offers only
      `wav_pcm16`; server picks PCM.
- [x] `test_client_hello_unsupported_closes_with_typed_error`.
- [x] `test_turn_id_present_on_all_turn_scoped_frames`.
- [x] `test_cancel_turn_echoes_turn_id`.
- [x] Option A only: `test_audio_chunk_prelude_precedes_each_binary` and
      `test_audio_chunk_bytes_match_binary_length`.
- [ ] Option B only: `test_no_binary_after_cancel_until_next_turn_started`.
- [x] Existing backend test suite unchanged on the web path (no `client_hello`
      sent → behavior identical to V05).

Checks:

- [x] Backend: full `pytest` passes (no regressions on existing 28+ tests).
- [ ] Web: no web-side change required; verify `npm run build` still passes
      only if any shared types were touched.

Commit reminder: commit at the end of Phase A1 with a message referencing
`docs/requirements/20260430_TODO_HERMES_VOICE_MOBILE_V06.md` and "Phase A1".

---

## Phase A2 — Backend: outbound encoder paths (AAC-ADTS + PCM passthrough)

Files likely touched:

- `api/app/audio/` (encoder selection / chunker)
- TTS bridge (wherever OpenAI TTS bytes are currently handed off)
- `api/tests/test_audio_encoders.py` (new)
- `api/requirements.txt` (only if an AAC encoder dep is added — prefer
  `pyav`/ffmpeg-bound options already common in deployment)

Tasks:

- [ ] Implement `wav_pcm16 @ 16 kHz mono` passthrough: emit raw 16-bit
      little-endian PCM frames at the negotiated rate, no container, no
      header. This is the mandatory fallback and must always be available.
- [ ] Implement `aac_adts @ 24 kHz mono` encoder path. Preserve the existing
      chunk-boundary heuristic so cancellation latency does not regress.
      Self-syncing ADTS framing must be honored — every emitted chunk must
      start on an ADTS frame boundary.
- [ ] Keep the existing Opus path intact for the web client. Do **not**
      change web behavior.
- [ ] If Option A was chosen in A1, emit the `audio_chunk` prelude with the
      exact `bytes` count of each encoder output chunk.

Tests:

- [ ] `test_pcm_passthrough_byte_exact_at_negotiated_rate`.
- [ ] `test_aac_adts_frames_decodable_by_reference_decoder` (CI uses a
      reference AAC decoder — `pyav` or equivalent — to confirm the bytes
      decode without errors).
- [ ] `test_chunk_boundaries_unchanged_vs_v05` (regression guard for cancel
      latency).
- [ ] `test_web_opus_path_unchanged`.

Checks:

- [ ] Backend: `pytest` passes.
- [ ] Manual: a smoke run against the deployed backend with a curl/script
      capture confirms AAC bytes are produced when `accepted_downlink_formats`
      includes `aac_adts`.

Commit reminder: reference this TODO file and "Phase A2".

---

## Phase A3 — Backend: end-user auth endpoints (carry-over from V05)

> Skip any task already shipped under prior TODOs; verify by grep before
> re-implementing. The point of this phase is to confirm the four endpoints
> exist, are tested, and behave per V05 §"Authentication for end users".

Tasks:

- [ ] `/api/auth/login` — email + password → triggers emailed 2FA code,
      returns a short-lived challenge handle.
- [ ] `/api/auth/verify` — challenge handle + 2FA code → sets host-only
      `hv_session` cookie on `hermes-voice.dashanddata.com`.
- [ ] `/api/auth/logout` — invalidates the session.
- [ ] `/api/auth/session` — returns current session status (used by the iOS
      app on launch to skip the login screen when a valid cookie exists).
- [ ] Confirm `hv_session` cookie attributes: `Secure`, `HttpOnly`,
      `SameSite=Lax` (or stricter), host-only, no `Domain=` attribute.
- [ ] Confirm `/ws/voice` accepts both cookie auth and bearer auth.

Tests:

- [ ] Endpoint-level pytest coverage for happy path, wrong password, wrong
      2FA code, expired challenge, double-use of a 2FA code.
- [ ] WebSocket auth test: connection succeeds with cookie, succeeds with
      bearer, fails without either.

Checks:

- [ ] Backend: `pytest` passes.

Commit reminder: reference this TODO file and "Phase A3".

---

## Phase M0a — Audio decode spike (Mac + physical iPhone) — gates M5

This phase intentionally runs **before** building the SwiftUI app shell, so a
decode failure cannot invalidate weeks of UI work. Use `scripts/audio_spike/`
or a throwaway Xcode target — do not pollute the main iOS target.

Tasks:

- [ ] Create `scripts/audio_spike/` (or a throwaway Xcode target under
      `mobile/ios/Spike/`) that:
  - [ ] Connects to the deployed `wss://hermes-voice.dashanddata.com/ws/voice`
        using a developer bearer key (this is allowed for the spike — bearer
        is still supported for dev/internal use).
  - [ ] Sends `client_hello` requesting `aac_adts` first.
  - [ ] Sends one canned `start_utterance` + tiny WAV upload + `end_of_utterance`.
  - [ ] Captures the entire binary downlink for one assistant turn into a
        local file.
  - [ ] Decodes that file end-to-end on a physical iPhone using **only**
        Apple built-in decoders (`AVAudioFile` / `AVAudioConverter`),
        schedules buffers on `AVAudioPlayerNode`, produces audible speech.
- [ ] Repeat the run for two consecutive turns with a Cancel between them.
      Confirm: no clicks, no trailing audio from the previous turn, no
      decoder-state contamination.
- [ ] If AAC fails on device: rerun the spike with `wav_pcm16` and
      authorize PCM as the V1 default.
- [ ] If both fail: stop and treat the backend as broken — do not introduce
      a third-party Opus dependency without explicit re-planning.
- [ ] Writeup at `docs/audio_spike/20260430_ios_downlink_spike.md` recording:
      chosen format, exact sample rate / channel count, decoder API used,
      observed latency from first byte to first audible sample, and any
      surprises.

Checks:

- [ ] Audible speech on iPhone speaker confirmed by Nick (not Simulator).
- [ ] Two-turn cancel run shows no audio leak.
- [ ] Writeup exists and names the format chosen for V1.

Commit reminder: commit the spike script and the writeup with a message
referencing this TODO file and "Phase M0a". Do **not** commit the throwaway
Xcode target if it pollutes the main project; keep it under
`scripts/audio_spike/` or a separate `mobile/ios/Spike/` folder excluded
from the production target.

---

## Phase M1 — Xcode project skeleton (Mac)

Files likely touched: `mobile/ios/HermesVoice/...`.

Tasks:

- [x] Create the Xcode project at `mobile/ios/HermesVoice/`. iOS 17 minimum.
      SwiftUI lifecycle. Async/await. No third-party SPM dependencies (the
      Opus carve-out is only added later if M0a authorized it).
- [x] App Transport Security: default-strict; only the production host is
      reachable in Release. Debug builds may permit a developer URL via
      Settings.
- [x] Folder layout: `App/`, `Auth/`, `Voice/` (protocol + socket + audio),
      `UI/`, `Settings/`. Match the V05 structure preserved by V06.
- [x] Configure schemes for Debug (allows bearer override + dev URL) and
      Release (cookie auth only, fixed production URL).
- [x] Add a stub Settings screen reachable in Debug only, exposing a
      `BackendURL` override stored in the user defaults / keychain as V05
      specifies.

Checks:

- [x] Xcode build succeeds for both Debug and Release schemes on the Mac.
- [x] Static analysis / SwiftLint (if configured) clean.

Commit reminder: reference this TODO file and "Phase M1".

---

## Phase M2 — Auth (Mac + simulator OK)

Tasks:

- [ ] `LoginView` — email + password.
- [ ] `VerifyView` — emailed 2FA code entry; supports paste.
- [ ] `AuthClient` — calls `/api/auth/login`, `/api/auth/verify`,
      `/api/auth/logout`, `/api/auth/session`. Cookie storage uses
      `HTTPCookieStorage` scoped to the production host.
- [ ] Keychain persistence of the session cookie per V05; no plaintext on
      disk.
- [ ] Launch flow: on app start, call `/api/auth/session`; if valid, skip
      directly to the main view.
- [ ] **Verify zero bearer key in Release.** Add a build-time assertion (or
      a CI check) that the `HERMES_VOICE_API_KEY` literal is not present in
      the Release binary's strings table.

Tests:

- [ ] Unit tests for `AuthClient` against a mocked `URLProtocol` covering
      login, verify, expired session, logout.
- [ ] Manual login + 2FA round-trip against the deployed backend on
      simulator.

Checks:

- [ ] Xcode tests pass for the auth target.
- [ ] Release build inspected for bearer literal — none present.

Commit reminder: reference this TODO file and "Phase M2".

---

## Phase M3 — WebSocket and protocol (Mac + simulator OK)

Tasks:

- [ ] `VoiceProtocol` — `Codable` Swift types for every JSON frame, including
      `turn_id` fields added in Phase A1. Unknown frames decode into a
      `Frame.unknown(rawJSON)` case and are logged but not crashed on.
- [ ] `VoiceSocket` — wraps `URLSessionWebSocketTask`. Sends `client_hello`
      with `accepted_downlink_formats` immediately after upgrade. Stores the
      negotiated `downlink_format`, `downlink_sample_rate`,
      `downlink_channels` from `session_started`.
- [ ] Implement the **chosen** audio-binding rule from Phase A1:
  - **Option A:** maintain a one-slot "expected next binary" state populated
    by each `audio_chunk` prelude. A binary frame arriving without a
    preceding prelude is a protocol error and is dropped with a logged
    warning.
  - **Option B:** maintain a "suppress binaries until next `turn_started`"
    flag set by `cancel_turn`.
- [ ] Render incoming JSON frames into the existing app state model:
      `session_started`, `turn_started`, `transcript`, `assistant_text`,
      `active_state`, `turn_end`/`turn_completed`, `voice_turn_skipped`,
      `error`, `pong`.
- [ ] Heartbeat / pong handling per V04.

Tests:

- [ ] Frame decode round-trip tests for every JSON frame including new
      `turn_id` fields.
- [ ] Fake-socket protocol tests:
  - Stale `audio_chunk` prelude (Option A) is dropped along with its paired
    binary; the next valid turn plays normally.
  - A binary frame arriving after `cancel_turn` is not delivered to the
    player, regardless of whether the server saw the cancel before emitting
    it.
  - Unknown JSON frames do not crash the decoder.

Checks:

- [ ] Xcode tests pass for the Voice target.

Commit reminder: reference this TODO file and "Phase M3".

---

## Phase M4 — Audio capture and uplink (Mac + physical iPhone)

Tasks:

- [ ] `AVAudioSession` configuration for record + playback (`.playAndRecord`,
      `.allowBluetooth` as needed); request mic permission with the iOS 17
      privacy strings.
- [ ] PTT capture via `AVAudioEngine` input tap. Encode/transmit per the V04
      uplink format (unchanged in V06).
- [ ] Send `start_utterance` / binary capture frames / `end_of_utterance`.
- [ ] Foreground-only behavior in V1: stop capture cleanly on background;
      tear down the engine.

Tests:

- [ ] Manual capture test on a physical iPhone: speak a sentence, confirm
      backend receives audible bytes (verified via backend log + transcript
      frame).

Checks:

- [ ] Permission prompt appears on first use; capture works on device.

Commit reminder: reference this TODO file and "Phase M4".

---

## Phase M5 — Audio playback and cancel (Mac + physical iPhone) — depends on M0a

Tasks:

- [ ] Implement the decode pipeline for the **negotiated** `downlink_format`
      only — `aac_adts` or `wav_pcm16`. No Opus path unless the M0a writeup
      explicitly authorized one and an SPM Opus dependency was added.
- [ ] `AVAudioPlayerNode` queue keyed by `turn_id`. Buffers from a turn that
      is no longer active are not scheduled; if already scheduled, are
      flushed via `playerNode.stop()` + `playerNode.reset()`.
- [ ] Cancel control:
  1. Stop local playback immediately (`stop()` + `reset()`).
  2. Send `{"event":"cancel_turn","turn_id":"<current>"}`.
  3. Optimistically transition `ActiveState` → `idle`.
  4. Filter subsequent inbound frames per Phase A1 Option A or B.
  5. Accept `turn_end` echoing the canceled `turn_id` as confirmation.
- [ ] Decoder-state hygiene between turns: a fresh decoder context per turn
      (or a verified reset path) so trailing samples from the prior turn
      cannot bleed forward.

Tests:

- [ ] iOS protocol test: a binary arriving after `cancel_turn` is never
      scheduled on the player.
- [ ] iOS protocol test: stale `audio_chunk` prelude (Option A) is dropped
      with its paired binary; next turn plays cleanly.
- [ ] End-to-end on a physical iPhone (manual): cancel during `thinking`,
      cancel during `speaking`, three back-to-back turns without leaks.

Checks:

- [ ] Xcode tests pass.
- [ ] Manual three-turn run on iPhone passes Acceptance Criterion #4.

Commit reminder: reference this TODO file and "Phase M5".

---

## Phase M6 — Connection UX (Mac + physical iPhone)

Tasks (unchanged from V05):

- [ ] Connection status indicator (connected / connecting / disconnected /
      auth-required).
- [ ] Reconnect with backoff on transient WebSocket failures; do not
      reconnect on auth failures (route to `LoginView` instead).
- [ ] Single visible active-state indicator transitioning through `idle →
      listening → thinking → speaking → idle` (and `awaiting_approval` if
      the backend exposes it).

Tests:

- [ ] Manual: drop wifi mid-turn; app reconnects, surfaces a clear status,
      and resumes accepting PTT after reconnect.

Checks:

- [ ] Xcode build + Xcode tests pass.

Commit reminder: reference this TODO file and "Phase M6".

---

## Phase M7 — Hardening (Mac + physical iPhone)

Tasks:

- [ ] Logging review per `docs/LOGGING_PYTHON_V06.md` for backend; iOS
      logging via `os.Logger` with no PII / no audio bytes / no bearer keys.
- [ ] Error surfacing per `docs/ERROR_REQUIREMENTS.md`: typed `error` frames
      from the backend render a user-readable message + a copyable error
      code; never a silent failure.
- [ ] **Re-run a smaller M0a-style spike against the Release build** to
      confirm the App-Store-distributable binary still decodes the chosen
      format on a physical device. Update the M0a writeup with the
      Release-build result.
- [ ] Battery / thermal sanity check: 10-minute continuous session does not
      pin the CPU or trigger thermal throttling on a current-gen iPhone.

Checks:

- [ ] All backend `pytest` passes.
- [ ] All Xcode tests pass.
- [ ] Release decode confirmed on device.

Commit reminder: reference this TODO file and "Phase M7".

---

## Phase M8 — TestFlight (Mac)

Tasks (unchanged from V05):

- [ ] App Store Connect record, bundle ID, signing, provisioning.
- [ ] Build, archive, upload, submit for internal TestFlight.
- [ ] Smoke test the TestFlight build on a physical iPhone: login + 2FA, one
      full PTT turn, one cancel, logout. Confirm no bearer literal in the
      uploaded `.ipa` (re-verify the Phase M2 check against the archive).

Checks:

- [ ] TestFlight build installs and runs on a physical iPhone.
- [ ] Acceptance criteria #1–#5 all hold against the TestFlight build.

Commit reminder: reference this TODO file and "Phase M8". Tag the commit
once V1 ships to TestFlight.

---

## Open questions to resolve during Phase A1 / M0a

Tracked here for visibility; any answer that diverges from the V06 default
must be recorded in `docs/PROTOCOL.md` (or equivalent) before downstream
phases proceed.

- Option A (per-chunk JSON prelude) vs Option B (suppress-until-next-turn).
  Default: **Option A**.
- AAC-ADTS vs PCM as the V1 default downlink. Default: **AAC-ADTS, PCM as
  the codified fallback**.
- Whether the web client should also send `client_hello` for symmetry.
  Default: **web unchanged in V06**.
- Whether `/api/auth/verify` should additionally return a JSON session token
  alongside the cookie. Default: **cookie-only**.
