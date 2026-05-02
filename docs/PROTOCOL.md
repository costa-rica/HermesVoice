# HermesVoice WebSocket Protocol

This document records the mobile V06 wire-contract additions for `/ws/voice`.

## Downlink negotiation

- iOS clients send `client_hello` immediately after WebSocket upgrade.
- The server chooses the first supported format from
  `accepted_downlink_formats`, preserving the client's preference order.
- Supported mobile formats in V06:
  1. `aac_adts` at 24000 Hz, mono.
  2. `wav_pcm16` at 16000 Hz, mono.
  3. `opus_ogg` at 24000 Hz, mono, retained for the existing web path.
- The web client may continue to omit `client_hello`; the server then uses the
  existing implicit Opus path and sends `downlink_format="opus_ogg"`.
- If no requested format is supported, the server sends an `error` frame with
  `code="unsupported_downlink"` and closes the socket.

The extended `session_started` frame is:

```json
{
  "event": "session_started",
  "session_id": "<persistent-voice-session-uuid>",
  "conversation_id": "<uuid>",
  "downlink_format": "aac_adts",
  "downlink_sample_rate": 24000,
  "downlink_channels": 1,
  "resumed": false,
  "created": true
}
```

`conversation_id` remains present for existing clients and is the Hermes
conversation id. When `client_hello.session_id` is provided and owned by the
authenticated caller, the server resumes that persistent voice session and
returns `resumed=true` and `created=false`. If `session_id` is omitted, the
server creates a new persistent voice session.

## Turn binding

- Every turn-scoped JSON frame carries `turn_id` as a string.
- `active_state` carries `turn_id` for turn-owned states such as `thinking`,
  `thinking_progress`, and `speaking`; `idle` is session-level and may omit it.
- `cancel_turn` accepts an optional `turn_id`. If absent, the server cancels
  the currently active turn. The resulting `turn_end` echoes the canceled
  turn id when one is known.

## Audio chunk binding decision

- V06 chooses Option A: a JSON `audio_chunk` prelude immediately precedes each
  binary audio WebSocket message.
- Rationale: Option A keeps binary frames as raw decoder input while giving
  the iOS client an explicit `turn_id`, byte count, format, and sequence
  number for stale-audio filtering.
- `seq` is monotonic within a turn and resets at zero for the next turn.
- `bytes` is the exact length of the following binary payload.

Example:

```json
{
  "event": "audio_chunk",
  "turn_id": "12",
  "seq": 0,
  "format": "aac_adts",
  "bytes": 4096
}
```
