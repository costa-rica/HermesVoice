# HermesVoice — Open-Source Mobile Integration Assessment

**Date:** 2026-04-30
**Branch:** dev_04_new_mobile
**Author:** Hermes agent
**Status:** Assessment complete — integration recommended via sherpa-onnx

---

## Context

The original HermesVoice native Swift/SwiftUI iOS app (deleted in commit `ae98501`)
was built from scratch. It reached a working state but required significant custom
plumbing for VAD, audio capture, and multi-turn lifecycle management. The goal of this
assessment is to determine whether adopting an existing open-source project — rather
than building from scratch again — is a better path to a hands-free, continuous-VAD
iOS client that streams to the existing public backend at
`https://hermes-voice.dashanddata.com`.

The backend is **not being recreated locally.** All testing targets the deployed
instance on avatar08 via the public HTTPS/WSS origin. The WebSocket voice protocol
is documented in `docs/PROTOCOL.md` and is already implemented on the server.

---

## Scope of Evaluation

The research doc (`docs/20260430hermesvoice-mobile-vad-research.md`) identified
several projects. Per the user's instruction, this assessment covers:

1. **sherpa-onnx** (k2-fsa/sherpa-onnx) — the research's primary recommendation
2. **FluidAudio** (FluidInference/FluidAudio) — the highest-ranked iOS-native alternative

---

## Project 1: sherpa-onnx (k2-fsa/sherpa-onnx)

**Repo:** https://github.com/k2-fsa/sherpa-onnx
**Stars:** ~12k | **License:** Apache-2.0 | **Last updated:** 2026-05-01
**Primary language:** C++ with official Swift/Kotlin/Python/C# bindings

### What it is

sherpa-onnx is a full on-device speech pipeline (VAD + streaming ASR + TTS) built
on ONNX Runtime. For HermesVoice we would use **only its VAD component** — the
Silero VAD ONNX model wrapped in a Swift API. The on-device STT and TTS are
irrelevant because the HermesVoice backend handles those.

### iOS Integration Maturity

| Capability | Status |
|---|---|
| Pre-built iOS xcframework | Yes — binary releases on GitHub, no compile-from-C++ required |
| Official Swift examples | Yes — `swift-api-examples/` in the repo, including microphone VAD |
| VAD API in Swift | Yes — `SherpaOnnxVad` class, speech start/end callbacks |
| Background audio | Compatible with `AVAudioSession .playAndRecord` |
| Minimum iOS | iOS 13+ (framework requirement) |
| Swift Package Manager | Not yet; xcframework is drop-in via Xcode |
| App binary size impact | ~25–35 MB added (xcframework + Silero VAD ONNX model ~2 MB) |

### How it would be used here

We do **not** adopt sherpa-onnx as a complete app. We use its iOS VAD demo
(`swift-api-examples/streaming-microphone-vad`) as a **skeleton**, then:

- Strip the on-device ASR/decoder path entirely
- Keep the `AVAudioEngine` tap + `SherpaOnnxVad` speech-start/speech-end logic
- Replace the on-device decode with a WebSocket stream to
  `wss://hermes-voice.dashanddata.com/ws/voice`
- Add HermesVoice auth (email + password + 2FA via `/api/auth/*`)
- Add TTS playback of binary audio frames returned by the backend
- Add multi-turn loop: after TTS finishes → re-arm VAD → next turn

### Feasibility: HIGH

The sherpa-onnx Swift VAD demo already does the hardest part: it captures mic audio
with `AVAudioEngine`, feeds 512-sample windows to the Silero model, fires callbacks
on `speech_start` and `speech_end`, and buffers the utterance. This is exactly what
the deleted HermesVoice Swift app had to implement manually. The plumbing we need to
**add** (WebSocket streaming, auth, TTS playback) is well-understood and maps directly
to the existing backend protocol.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| xcframework adds ~30 MB to app | Low | Acceptable for V1; strip debug symbols for release |
| ONNX model must ship in bundle or download on first run | Low | Bundle the 2 MB model; no CDN dependency |
| VAD API surface may change across sherpa-onnx releases | Medium | Pin to a specific release tag; upgrade deliberately |
| sherpa-onnx VAD calibration (sensitivity) requires tuning | Low | Silero is well-regarded; existing example shows how to set thresholds |

---

## Project 2: FluidAudio (FluidInference/FluidAudio)

**Repo:** https://github.com/FluidInference/FluidAudio
**Stars:** ~1.9k | **License:** Apache-2.0 | **Last updated:** 2026-05-01
**Primary language:** Swift

### What it is

FluidAudio is a Swift package that wraps frontier CoreML audio models — including
VAD, ASR, TTS, and speaker diarization — using Apple's Neural Engine. It is purely
Swift, uses CoreML (not ONNX), and integrates via Swift Package Manager.

### iOS Integration Maturity

| Capability | Status |
|---|---|
| Swift Package Manager | Yes — clean SPM integration |
| VAD specifically | Yes — listed as a core feature |
| CoreML / Apple Neural Engine | Yes — runs on ANE for power efficiency |
| Official demo app | Minimal; API examples in README only |
| Microphone streaming demo | Not documented as of this assessment |
| Background audio | Depends on AVFoundation (compatible) |
| App binary size impact | Minimal (Swift package, CoreML models downloaded separately) |
| Community/documentation | Sparse — early-stage project |

### How it would be used here

Similar pattern: use the VAD API to detect speech start/end, stream audio to
the HermesVoice WebSocket, play back binary TTS audio. The clean SPM integration
and no-xcframework approach are appealing for maintainability.

### Feasibility: MODERATE

FluidAudio is the cleaner architectural choice (native Swift, no C++ blobs,
CoreML uses ANE for battery efficiency). However, the project is significantly
newer with 6× fewer users. The absence of a documented microphone streaming + VAD
demo means we would be doing more discovery work versus adapting a known-working
example. The VAD API may not yet be stable. For a project that already suffered
from a from-scratch build failure mode, starting with sparser documentation is
a real risk.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| No streaming microphone VAD demo | Medium | Must write mic capture + VAD loop from scratch |
| Smaller community, less battle-tested | Medium | 1.9k stars is not tiny, but 12k is more confidence |
| API may change across early releases | Medium | Pin to a specific version |
| CoreML model file management | Low | SPM can pull models; but first-run download adds latency |

---

## Comparison Summary

| Criterion | sherpa-onnx | FluidAudio |
|---|---|---|
| Stars / community | 12k — large | 1.9k — growing |
| iOS VAD demo to start from | Yes — mic streaming VAD example | No — must write from scratch |
| Integration friction | xcframework drop-in | SPM (simpler tooling) |
| Binary size impact | ~30 MB | Minimal |
| Tech stack purity | C++ under the hood | Pure Swift / CoreML |
| Battery / ANE optimization | ONNX Runtime (good but not ANE) | CoreML ANE (excellent) |
| Documentation quality | Extensive | Sparse |
| Risk for HermesVoice V1 | Low | Medium |

---

## Verdict

**Use sherpa-onnx as the foundation for the HermesVoice iOS app.**

The decisive factor is the existence of a **working iOS microphone VAD demo in
Swift** that we can adapt rather than author. The deleted HermesVoice Swift app
demonstrated that writing VAD + audio lifecycle + WebSocket integration from
scratch is where subtle bugs accumulate. sherpa-onnx gives us the hard VAD
plumbing pre-tested. The C++ overhead and app-size tradeoff are acceptable for V1.

FluidAudio should be revisited for V2 once its API stabilizes and a streaming
microphone example exists — the CoreML/ANE path is architecturally superior for
a production iOS product.

---

## Integration Plan (Loose)

This plan targets the `dev_04_new_mobile` branch. The backend at
`https://hermes-voice.dashanddata.com` is the only target — no local Python
backend is needed unless the `/api/auth/*` endpoints or `/ws/voice` protocol need
changes.

### Phase 0 — Environment setup (Mac, no Xcode build yet)

1. Download the latest sherpa-onnx iOS xcframework release from GitHub releases.
2. Identify the `swift-api-examples/streaming-microphone-vad` demo as the starting
   point (or the nearest equivalent in the release).
3. Verify the demo builds and runs on Simulator to confirm the xcframework and
   Silero VAD model file are correctly wired.
4. Run the VAD demo on a physical iPhone with mic input to confirm speech-start /
   speech-end callbacks fire correctly.

**Deliverable:** VAD fires on real speech on a physical iPhone. No HermesVoice
code yet.

### Phase 1 — New Xcode project scaffold (`mobile/ios/`)

1. Create a new SwiftUI iOS 17+ Xcode project at `mobile/ios/HermesVoice.xcodeproj`.
2. Add the sherpa-onnx xcframework as a linked binary.
3. Bundle the Silero VAD ONNX model file into the app target.
4. Re-implement the `AVAudioEngine` mic tap + `SherpaOnnxVad` VAD loop from the
   demo into a `VoiceActivityDetector` Swift actor.
5. Wire Background Audio capability plist entry and `AVAudioSession`
   `.playAndRecord` + `.mixWithOthers` so VAD runs with screen off.
6. Smoke test: confirm VAD still fires on device with screen off.

**Deliverable:** App with working on-device VAD, no networking yet.

### Phase 2 — Auth layer

1. Implement `AuthService` using `URLSession` against:
   - `POST /api/auth/login` → email + password
   - `POST /api/auth/verify` → 6-digit email 2FA code
   - `GET /api/auth/session` → session check on launch
   - `POST /api/auth/logout`
2. Store `hv_session` cookie in Keychain (not UserDefaults).
3. SwiftUI login / 2FA screens with minimal UI.
4. Redirect to voice screen on session established; back to login on auth failure.
5. Test manually against `https://hermes-voice.dashanddata.com` — **no mock**.

**Deliverable:** App logs in and persists session against the live backend.

### Phase 3 — WebSocket voice protocol

1. Implement `VoiceSocket` over `URLSessionWebSocketTask` at
   `wss://hermes-voice.dashanddata.com/ws/voice`.
2. Implement Codable frame types from `docs/PROTOCOL.md`:
   - Outbound: `client_hello`, `start_utterance`, `end_of_utterance`, `cancel_turn`
   - Inbound: `session_started`, `turn_started`, `transcript`, `assistant_text`,
     `active_state`, `audio_chunk` (prelude), binary frames, `turn_end`, `error`
3. On WebSocket open, send `client_hello` with `accepted_downlink_formats:
   ["aac_adts", "wav_pcm16"]`.
4. Store the negotiated `downlink_format` from `session_started`.
5. Implement stale-audio filtering: Option A — track `turn_id` from `audio_chunk`
   prelude; drop binary frames whose prelude `turn_id` differs from the current
   active turn.
6. Unit-test frame parsing and stale-frame suppression with a fake socket.

**Deliverable:** App connects to live backend WebSocket and parses protocol frames.

### Phase 4 — Audio uplink: VAD → WebSocket

1. Connect `VoiceActivityDetector` callbacks to `VoiceSocket`:
   - `speech_start` → send `start_utterance` + begin streaming PCM chunks as
     binary WebSocket messages (16 kHz, 16-bit mono).
   - `speech_end` → send `end_of_utterance`.
2. Buffer the in-flight PCM into 20 ms frames; flush on `speech_end`.
3. Test on physical iPhone: speak → confirm backend receives non-empty utterance
   and returns a turn response.

**Deliverable:** End-to-end uplink: VAD detects speech → audio reaches backend.

### Phase 5 — Audio downlink: TTS playback

1. Implement `AudioPlayer` using `AVAudioPlayerNode` scheduled on `AVAudioEngine`.
2. On `audio_chunk` prelude: note `turn_id`, `format`, `bytes`, `seq`.
3. On following binary frame: decode per `downlink_format`:
   - `aac_adts`: feed to `AVAudioConverter` → `AVAudioPCMBuffer` → schedule on node.
   - `wav_pcm16`: wrap directly in `AVAudioPCMBuffer` → schedule on node.
4. On `turn_end`: flush playback queue.
5. On `cancel_turn` sent: call `playerNode.stop()` + `playerNode.reset()`, drop
   subsequent frames for the canceled `turn_id`.
6. Test back-to-back turns and mid-turn cancellation on device.

**Deliverable:** App speaks Hermes responses aloud; cancellation works cleanly.

### Phase 6 — Multi-turn loop and UX polish

1. After TTS playback ends (player queue drains): auto re-arm VAD, update UI to
   show listening state.
2. Implement visible connection states: `idle`, `listening`, `thinking`, `speaking`,
   `reconnecting`.
3. Implement WebSocket reconnect with exponential backoff (initial 1s, cap 30s).
4. Re-auth if WebSocket close code indicates session expiry.
5. Test full hands-free conversation: speak → hear response → speak again, 3+
   turns, screen off during at least one.

**Deliverable:** Hands-free multi-turn loop works end-to-end against live backend.

### Phase 7 — Hardening and TestFlight

1. Verify no secrets, `.env` files, or bearer tokens are in the bundle.
2. Confirm configured backend URL is not localhost in any build scheme.
3. Verify background audio keeps working after a phone call interruption
   (`AVAudioSessionInterruptionNotification`).
4. Instrument logging (os.log) to aid debugging without leaking PII.
5. Archive build → TestFlight.

---

## Backend Changes Required

The existing backend protocol in `docs/PROTOCOL.md` is complete for V06.
No backend changes are expected to be needed **unless**:

- `client_hello` / `downlink_format` negotiation is not yet implemented in the
  live avatar08 instance — verify by connecting a test WebSocket client and
  checking `session_started` for a `downlink_format` field.
- The `/api/auth/*` login endpoints (`login`, `verify`, `logout`, `session`)
  don't yet exist as documented — check the live origin.

Both of these should be verified in Phase 2–3 before building the iOS auth and
protocol layers. If either is missing, that is the only case where a local backend
setup note would be needed — flag it and address it on avatar08 directly.

---

## Key Assumptions

- `https://hermes-voice.dashanddata.com` is accessible from the development
  iPhone without VPN or IP allowlist.
- The live backend has `client_hello` / AAC / PCM downlink negotiation already
  deployed (per V06 plan), or the scope falls back to PCM-only.
- The existing Keychain / SwiftUI auth pattern from V05/V06 plans applies.
- sherpa-onnx xcframeworks are available as binary releases — no C++ build chain
  required on the development Mac.

---

## References

- Research doc: `docs/20260430hermesvoice-mobile-vad-research.md`
- Backend agent instructions: `docs/20260430 Mobile App Public Backend Agent Instructions.md`
- Protocol reference: `docs/PROTOCOL.md`
- V06 mobile plan: `docs/archived/20260430_HERMES_VOICE_PLAN_V06_MOBILE.md`
- sherpa-onnx repo: https://github.com/k2-fsa/sherpa-onnx
- FluidAudio repo: https://github.com/FluidInference/FluidAudio
