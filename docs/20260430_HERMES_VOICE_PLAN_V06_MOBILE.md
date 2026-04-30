# HermesVoice — Plan V06 (Native iOS Mobile)

**Date:** 2026-04-30 (America/Los_Angeles)
**Supersedes:** `docs/20260430_HERMES_VOICE_PLAN_V05_MOBILE.md` in full.
**Companion plan:** V04 remains authoritative for backend, web, and deployment
except where this document tightens the wire contract.
**Scope:** Native Swift/SwiftUI iOS app for HermesVoice.

V06 keeps the V05 product decisions intact — a native Swift/SwiftUI iOS app,
the single public origin `https://hermes-voice.dashanddata.com`, and end-user
email + password + emailed-2FA auth instead of an embedded bearer API key —
and corrects two architecturally load-bearing risks the V05 Codex assessment
identified:

1. **Mobile downlink audio is not yet provably decodable on iOS.** V06 adds an
   explicit format-negotiation / fallback strategy and a physical-device
   validation spike before any code commits to Opus-only native playback.
2. **Cancellation / stale-audio handling cannot be implemented under V04's
   wire contract** because outbound binary frames carry no turn metadata. V06
   extends the protocol so the client can either tag audio with `turn_id` or
   apply a simpler "suppress until next `turn_started`" rule.

The V05 host model, auth model, project layout, and active-state mapping are
preserved verbatim except where the corrections require small changes; those
are called out explicitly below.

---

## What is preserved from V05

- **Single public host, path-based routing.** All client traffic goes to
  `https://hermes-voice.dashanddata.com`. There is no `api.` subdomain.
- **End-user auth.** Shipped iOS binaries authenticate the human user via
  permitted email + password + emailed numeric 2FA code. The backend bearer
  `HERMES_VOICE_API_KEY` is **never** embedded in App Store / TestFlight
  builds; it remains supported for internal scripts, dev builds, and
  service-to-service callers only.
- **Native iOS primitives.** `URLSessionWebSocketTask`, `AVAudioEngine` /
  `AVAudioRecorder`, `AVAudioSession`, and `AVAudioPlayerNode` replace the
  browser equivalents.
- **iOS app structure** (`mobile/ios/HermesVoice/...`), iOS 17 minimum,
  SwiftUI, async/await, no third-party SDKs by default — see "Dependency
  policy" below for the audio-decode carve-out.
- **State machine** mirrors V04 `active_state` 1:1, including
  `awaiting_approval`.
- **URL derivation, ATS rules, cookie/session strategy, JSON auth endpoints
  (`/api/auth/login`, `/api/auth/verify`, `/api/auth/logout`,
  `/api/auth/session`), Keychain persistence, and Settings override** are
  unchanged from V05.

Where V05 sections are unchanged, V06 incorporates them by reference rather
than restating them. Treat V05 § "Host model and URL derivation",
§ "Authentication for end users", § "iOS app structure", and § "Backend /
public deployment changes" as in force, with the corrections in the next two
sections layered on top.

---

## Correction 1 — Mobile downlink audio: format negotiation, fallback, and a physical-device spike

### Why this changes

V05 assumed iOS would natively decode the backend's outbound TTS bytes — which
on the web side are treated as `audio/ogg; codecs=opus` — using
`AVAudioConverter` and `AVAudioPlayerNode`, with no third-party SDKs. That is
not a safe V1 assumption:

- Apple platforms do not ship a first-class Ogg/Opus container decoder for
  arbitrary streaming chunks via `AVAudioConverter`. Decoding requires either
  CoreAudio's narrow set of supported file formats, an Opus library
  (`libopus` + an Ogg demuxer or raw Opus packet framing), or transcoding on
  the server.
- The current backend emits raw binary frames whose internal framing
  (Ogg pages vs. raw Opus packets, presence/absence of an `OpusHead`/
  `OpusTags` preamble, chunk independence, sample-rate assumptions) is not
  documented at the wire level for a non-browser consumer.
- If native decoding fails after M5 ships, the core product breaks: Hermes
  can hear the user but the iPhone cannot reliably speak back.

V06 treats this as a discovery item that must close before any code path
commits to Opus-only native playback.

### What V06 requires

#### 1.1 Explicit downlink format negotiation in the wire contract

The session opener gains a negotiated downlink format. On WebSocket open, the
client sends a capability hint and the server confirms an authoritative
choice in `session_started`:

Client → server (immediately after upgrade):

```json
{
  "event": "client_hello",
  "client": "ios",
  "client_version": "<semver>",
  "accepted_downlink_formats": ["aac_adts", "mp3", "wav_pcm16", "opus_ogg"]
}
```

Server → client (existing event, extended):

```json
{
  "event": "session_started",
  "conversation_id": "<uuid>",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1
}
```

Format identifiers and their iOS decode paths:

| `downlink_format` | Container / framing                | iOS decoder                                      |
|-------------------|------------------------------------|--------------------------------------------------|
| `aac_adts`        | AAC in ADTS frames (self-syncing)  | `AVAudioFile` / `AVAudioConverter` (built-in)    |
| `mp3`             | MPEG-1 Layer III frames            | `AVAudioConverter` (built-in)                    |
| `wav_pcm16`       | Headerless raw PCM 16-bit LE       | Direct `AVAudioPCMBuffer` fill (built-in)        |
| `opus_ogg`        | Ogg-encapsulated Opus              | Requires `libopus` + Ogg demux (third-party)     |

Servers that cannot honor any client-accepted format must close the socket
with a typed `error` frame (`code="unsupported_downlink"`) rather than
silently emitting bytes the client cannot decode.

The web client continues to receive whatever it accepts today
(`opus`/Ogg-Opus); web behavior is unchanged. Mobile clients are the new
caller for which negotiation matters.

#### 1.2 Default mobile downlink: AAC-ADTS, with PCM fallback

V06 makes `aac_adts @ 24 kHz mono` the **default** mobile downlink because:

- AAC is decoded natively by AVFoundation without third-party code.
- ADTS framing is self-synchronizing; chunked WebSocket delivery is safe
  without a custom demuxer.
- 24 kHz mono is the OpenAI TTS native rate — no resampling required
  server-side beyond what already happens.

`wav_pcm16 @ 16 kHz mono` is the **mandatory fallback** that every server
build must support. PCM is trivially decodable on every platform and is the
escape hatch if AAC encoding ever regresses on the server. It costs ~10× the
bandwidth of AAC but is acceptable for a fallback path.

`opus_ogg` remains optional and is only used if the device-spike below
demonstrates a working pipeline **and** an explicit decoder dependency is
added (see § Dependency policy).

#### 1.3 Physical-device validation spike (gates M5)

A new milestone, **M0a — Audio decode spike**, is added before M5. It blocks
M5 and is performed on Nick's MacBook Air with a real iPhone (not Simulator,
because Simulator audio routing diverges from device behavior on AVAudioEngine
edge cases).

M0a deliverables:

- A throwaway Xcode target (or a script in `scripts/audio_spike/`) that:
  1. Connects to the deployed backend `wss://.../ws/voice` using a developer
     bearer key.
  2. Sends one canned `start_utterance` + tiny WAV + `end_of_utterance`.
  3. Captures the entire binary downlink for one assistant turn into a file.
  4. Decodes that file end-to-end using **only** Apple's built-in decoders
     for the chosen `downlink_format`, schedules buffers on
     `AVAudioPlayerNode`, and produces audible speech on the iPhone speaker.
- The same exercise repeated for at least two turns back-to-back with a
  Cancel between them, to confirm decoder-state reset (no clicks, no
  trailing audio from the previous turn).
- A short writeup at `docs/audio_spike/20260430_ios_downlink_spike.md`
  recording: chosen format, exact sample-rate / channel count, decoder API
  used, observed latency from first byte to first audible sample, and any
  surprises.

If the spike fails for AAC, V06 falls back to `wav_pcm16` and the project
ships PCM downlink for V1; AAC remains a server optimization to revisit
later. If the spike fails for both AAC and PCM, the backend is broken and
that is the bug to fix — there is no native-decode workaround.

The spike does **not** depend on having the iOS app shell, auth flow, or
SwiftUI views built. It is intentionally placed early so a decode failure
cannot invalidate weeks of UI work.

### Backend work this implies

- Implement `client_hello` handling and `downlink_format` selection in
  `/ws/voice`.
- Implement an AAC-ADTS encoder path for outbound TTS chunks (likely
  ffmpeg/`pyav`, or a managed AAC encoder), preserving the existing chunking
  heuristic boundaries so cancellation latency is unchanged.
- Implement a PCM-passthrough path (`wav_pcm16`) — trivial: emit raw 16-bit
  little-endian PCM frames at the negotiated sample rate, no container.
- Keep the existing Opus path for the web client; do **not** force the web
  client into renegotiation in V06.
- Add backend tests covering: unknown requested format → error close;
  intersection-empty → `unsupported_downlink`; AAC frames decodable by a
  reference decoder in CI; PCM frames byte-exact at the chosen rate.

### Dependency policy

The "no third-party SDKs in V1" rule from V05 is retained for **everything
except audio decode**, and even there only if `opus_ogg` is selected. The
default AAC and PCM paths require zero third-party code on iOS. If a future
revision of the project decides Opus is worth the complexity, a maintained
Opus library (e.g., `swift-opus`/`libopus` via SPM) is permitted for that
specific module.

---

## Correction 2 — Cancellation and stale-audio handling: protocol changes

### Why this changes

V05 specifies that the iOS client should "tag each scheduled buffer with the
active `turnId`" and "drop any binary frames received after the cancel that
carry the now-stale `turnId`." Under the V04 wire contract this is
unimplementable: outbound binary frames are raw audio bytes with no per-frame
metadata, and turn ids are an internal backend concept that never appears on
the wire alongside audio chunks.

V06 closes this gap by extending the wire contract so cancellation correctness
is achievable from the client side.

### Wire-contract additions

#### 2.1 `turn_id` is now a first-class wire field

Every turn-scoped JSON frame carries a `turn_id` string. Specifically:

- `turn_started` includes `turn_id`.
- `active_state` includes `turn_id` whenever the state belongs to a turn
  (i.e., not `idle`).
- `transcript`, `assistant_text`, `thinking_progress`,
  `voice_turn_skipped`, and `turn_end` / `turn_completed` include
  `turn_id`.
- `cancel_turn` (client → server) accepts an optional `turn_id`; if absent,
  the server cancels the currently active turn. The server's response
  `turn_end` (or equivalent) echoes the `turn_id` actually canceled.

Existing fields are preserved; this is additive.

#### 2.2 Audio chunks gain a turn binding — pick exactly one

V06 mandates one of the two following shapes. The implementation chooses
**Option A** by default; Option B is documented as an acceptable simpler
alternative if the team would rather not change binary framing.

##### Option A (default) — Audio prelude JSON before each binary chunk

The server sends a JSON `audio_chunk` envelope immediately before each binary
frame:

```json
{
  "event": "audio_chunk",
  "turn_id": "<uuid>",
  "seq": 0,
  "format": "aac_adts",
  "bytes": 4096
}
```

The very next WebSocket message must be a binary frame whose payload length
matches `bytes`. The client maintains a small one-slot "expected next binary"
state: when a binary frame arrives without a preceding `audio_chunk` prelude,
the client treats it as a protocol error and drops it. `seq` is monotonic
within a turn and resets per turn; clients may use it for diagnostics but are
not required to reorder.

This keeps binary frames as raw decoder input (no envelope parsing on the hot
path) while giving every chunk a turn binding for cancellation logic.

##### Option B — "Suppress until next `turn_started`" rule

If Option A is not implemented, the server guarantees:

- After receiving `cancel_turn`, the server emits **no further binary frames
  belonging to the canceled turn**, and emits a `turn_end` (or equivalent)
  JSON frame with the canceled `turn_id`.
- The client, upon sending `cancel_turn`, ignores all incoming binary frames
  until it observes the next `turn_started` JSON frame.

This rule is simpler to implement client-side but pushes a hard ordering
guarantee onto the server: it must drain or discard any in-flight TTS bytes
in its outbound queue before continuing. It also makes mid-turn binary
"leakage" undetectable in tests, so Option A is preferred where the backend
queue can be paused cheaply.

V06 declares **Option A** the implementation target; Option B is the
documented fallback if encoder/queue plumbing makes Option A impractical
within the M5 window. Whichever is chosen, the chosen rule is recorded in
`docs/PROTOCOL.md` (or the equivalent contract doc) before M5 starts.

#### 2.3 Client-side cancellation procedure (updated)

The iOS Cancel control:

1. **Stops local playback immediately** — `playerNode.stop()` and
   `playerNode.reset()` flush queued PCM buffers.
2. Sends `{"event":"cancel_turn","turn_id":"<current>"}` over the socket.
3. Optimistically transitions `ActiveState` to `idle`.
4. **Filters subsequent inbound frames**:
   - Under Option A: drops any `audio_chunk` (and its paired binary) whose
     `turn_id` does not match the currently active turn — including frames
     for the just-canceled turn that were already in flight.
   - Under Option B: ignores all binary frames until the next `turn_started`.
5. Accepts `turn_end` with the canceled `turn_id` (and a final
   `active_state=idle`) as confirmation.

### Tests this implies

- Backend test: cancel during `thinking` — no further binary frames for the
  canceled turn after the server acks `cancel_turn`; `turn_end.turn_id`
  matches the canceled turn.
- Backend test: cancel during `speaking` — same guarantee, plus the next
  `turn_started` carries a fresh `turn_id`.
- iOS protocol test (using a fake socket): a binary frame arriving after
  `cancel_turn` is not scheduled on the player, regardless of whether it was
  emitted before or after the server saw the cancel.
- iOS protocol test: a stale `audio_chunk` prelude (Option A) is dropped
  along with its paired binary, and the next valid turn plays normally with
  no decoder-state contamination.

These tests are added to M3 (protocol) and M5 (cancel/playback) milestones.

---

## Revised milestones

The phase numbering continues from V04 / V05. The only structural changes
versus V05 are the new **M0a** spike, the M0 backend additions, and the
M3/M5 protocol-test additions.

### M0 — Backend prep on Ubuntu (no Xcode required)
- [ ] Add `/api/auth/login`, `/api/auth/verify`, `/api/auth/logout`,
      `/api/auth/session` JSON endpoints (unchanged from V05).
- [ ] Confirm `hv_session` cookie is host-only on
      `hermes-voice.dashanddata.com`.
- [ ] Confirm `/ws/voice` accepts cookie auth and bearer auth.
- [ ] **New:** Implement `client_hello` handling and `downlink_format`
      selection in `/ws/voice`. Default to `aac_adts @ 24 kHz mono`; PCM
      fallback (`wav_pcm16 @ 16 kHz mono`) mandatory.
- [ ] **New:** Implement AAC-ADTS encoder path and PCM passthrough path for
      outbound TTS chunks; preserve existing chunk boundaries.
- [ ] **New:** Add `turn_id` to `turn_started`, `active_state` (when
      turn-scoped), `transcript`, `assistant_text`, `thinking_progress`,
      `voice_turn_skipped`, `turn_end`/`turn_completed`. `cancel_turn`
      accepts optional `turn_id`.
- [ ] **New:** Implement Option A (audio_chunk prelude before each binary
      frame) **or** Option B (suppress-until-next-`turn_started`). Record
      choice in protocol doc.
- [ ] Backend tests for auth endpoints, format negotiation, and cancel
      semantics under the chosen Option.

### M0a — Audio decode spike (Mac + iPhone, **gates M5**)
- [ ] Throwaway target / script that captures one full assistant-turn
      downlink against the deployed backend at the negotiated default
      format (`aac_adts`).
- [ ] Decode end-to-end on a physical iPhone using only Apple built-in
      decoders. Confirm audible playback.
- [ ] Repeat with two consecutive turns and a Cancel between them; confirm
      no audio leaks across turns and no decoder-state artifacts.
- [ ] If AAC fails: repeat with `wav_pcm16` and ship PCM in V1.
- [ ] Writeup at `docs/audio_spike/20260430_ios_downlink_spike.md`.

### M1 — Xcode project skeleton (Mac)
Unchanged from V05.

### M2 — Auth (Mac)
Unchanged from V05.

### M3 — WebSocket and protocol (Mac)
- [ ] Implement `VoiceProtocol` Codable frames including `turn_id` fields.
- [ ] Implement `VoiceSocket` over `URLSessionWebSocketTask`.
- [ ] Send `client_hello` with `accepted_downlink_formats` on connect;
      store the negotiated `downlink_format` from `session_started`.
- [ ] Render `session_started`, `turn_started`, `transcript`,
      `assistant_text`, `active_state`, `turn_end`/`turn_completed`,
      `voice_turn_skipped`, `error`, `pong`.
- [ ] Implement the chosen audio-binding rule (Option A prelude state
      machine, or Option B suppression flag).
- [ ] Ignore unknown JSON frames safely.
- [ ] Protocol tests for stale-frame filtering during cancel.

### M4 — Audio capture and uplink (Mac + iPhone)
Unchanged from V05.

### M5 — Audio playback and cancel (Mac + iPhone)
- [ ] Decode pipeline for the **negotiated** `downlink_format` only
      (`aac_adts` or `wav_pcm16`). No Opus path unless M0a explicitly
      authorized one.
- [ ] `AVAudioPlayerNode` queue keyed by `turn_id`.
- [ ] Cancel: `stop()` + `reset()`, send `cancel_turn` with `turn_id`,
      filter subsequent stale frames per the chosen Option.
- [ ] End-to-end tests: cancel during `thinking`, cancel during `speaking`,
      back-to-back turns.

### M6 — Connection UX (Mac + iPhone)
Unchanged from V05.

### M7 — Hardening (Mac + iPhone)
Unchanged from V05, plus:
- [ ] Re-run a smaller version of the M0a spike against the Release build to
      confirm the App-Store-distributable binary still decodes the chosen
      format on a physical device.

### M8 — TestFlight (Mac)
Unchanged from V05.

---

## Open questions to resolve during M0 / M0a

- Does the server team prefer Option A (per-chunk JSON prelude) or Option B
  (suppress-until-next-`turn_started`)? Default in this plan: **Option A**.
- Is AAC-ADTS encoding cheap enough server-side to be the default, or should
  PCM be the V1 default (simpler, higher bandwidth)? Default: **AAC-ADTS,
  with PCM as the codified fallback**.
- Should the web client also begin sending `client_hello` for symmetry, or
  remain on its current implicit Opus path? Default: **web unchanged in V06**.
- Should `/api/auth/verify` additionally return a JSON session token
  alongside the cookie? Default: **cookie-only** (carried over from V05).

---

## Cross-references

- V05 plan (superseded): `docs/20260430_HERMES_VOICE_PLAN_V05_MOBILE.md`.
- V05 Codex assessment: `docs/20260430_HERMES_VOICE_PLAN_V05_MOBILE_ASSESSMENT_CODEX.md`.
- V04 plan (still authoritative for backend/web/deployment except where this
  plan tightens the wire contract):
  `docs/20260428_HERMES_VOICE_PLAN_V04.md`.
- Logging standard: `docs/LOGGING_PYTHON_V06.md`.
- Error standard: `docs/ERROR_REQUIREMENTS.md`.
