# HermesVoice Plan V05 Mobile - Codex Architecture Assessment

## Finding 1 - iOS downlink playback is not de-risked

**Severity:** Fatal project risk for native mobile parity.

V05 requires iOS to play backend binary frames where each frame is an OpenAI
TTS `opus` response, decoded by `AVAudioConverter`, with no third-party SDKs.
That is not a safe iOS V1 assumption. The current backend/web contract treats
the bytes as `audio/ogg; codecs=opus` on the web side, while the iOS plan does
not define an Apple-supported container, packet framing, magic cookie handling,
or fallback format. If native decoding fails, M5 blocks the core product: Hermes
can hear the user but the iPhone cannot reliably speak back.

**Recommended correction:**

- Make M0 include a physical-device spike that proves one complete backend TTS
  binary frame can be decoded and scheduled on iOS using the exact shipped
  backend bytes.
- Until that proof exists, do not make Opus-only native playback a V1
  dependency. Add a mobile-safe downlink option now, preferably negotiated in
  `session_started` or `start_utterance`, such as `mp3`, `aac/m4a`, or another
  AVFoundation-supported format/container.
- If Opus remains required, explicitly add a maintained Opus/Ogg decoder
  dependency and define frame boundaries, codec headers, and reset behavior
  for independent TTS chunks. Remove the "no third-party SDKs in V1" constraint
  for audio decode.

## Finding 2 - Stale-audio cancellation depends on missing turn metadata

**Severity:** Major success risk for cancellation correctness.

V05 says the iOS client should tag scheduled buffers with `turnId` and drop
binary frames whose `turnId` is stale after cancel. The inherited V04/backend
contract does not expose a turn id to the client, and binary WebSocket frames
are raw audio bytes with no per-frame metadata. The backend uses turn ids
internally, but outbound frames only include generic events such as
`turn_started`, `active_state`, `turn_completed`, and raw binary audio. A native
implementation following V05 literally cannot implement the stated stale-frame
guard.

**Recommended correction:**

- Extend the WebSocket contract before M3/M5 so every turn-scoped JSON frame
  includes `turn_id`, and every audio chunk is associated with a turn. Practical
  options:
  - send `{"event":"audio_chunk","turn_id":"...","format":"...","seq":N}`
    before each following binary frame; or
  - replace raw binary frames with an envelope format that carries
    `turn_id`, `seq`, `format`, and bytes; or
  - guarantee that after `cancel_turn` the client suppresses all audio until a
    fresh `turn_started` with a new `turn_id`, and document that simpler state
    rule instead of per-frame turn tagging.
- Add backend and iOS protocol tests for cancel during `thinking` and
  `speaking`, verifying late audio from the canceled turn cannot be scheduled
  and the next valid turn can play normally.
