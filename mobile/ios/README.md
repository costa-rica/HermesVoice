# HermesVoice iOS

This directory contains the native SwiftUI iOS app scaffold for HermesVoice.

## Backend origin

The default backend origin is:

1. `https://hermes-voice.dashanddata.com`

The app derives the voice WebSocket URL from the same origin:

1. `wss://hermes-voice.dashanddata.com/ws/voice`

During development, the backend origin can be overridden from the iOS Settings app using:

1. HermesVoice
2. Backend Origin

The app also has a developer-only bearer-token setting:

1. HermesVoice
2. Developer Bearer Token

Debug builds allow local HTTP origins for local API testing. Release builds still refuse non-HTTPS and localhost/LAN origins.

For iOS Simulator with the local API running on this Mac:

1. Set Backend Origin to `http://127.0.0.1:8700`.
2. Set Developer Bearer Token to the local value configured by the API agent.
3. Relaunch HermesVoice and press Start.

For a physical iPhone, `127.0.0.1` points at the phone, not the Mac. To test against a backend on this Mac:

1. Start the API on a LAN-visible host, for example `uvicorn app.main:app --reload --host 0.0.0.0 --port 8700`.
2. Find the Mac LAN IP.
3. Set Backend Origin to `http://<mac-lan-ip>:8700`.
4. Keep the phone and Mac on the same network.
5. Set Developer Bearer Token to the local value configured by the API agent.

## Current scaffold

1. `mobile/ios/HermesVoice/HermesVoice.xcodeproj` is a SwiftUI iOS project.
2. `VoiceActivityDetector.swift` wraps sherpa-onnx Silero VAD behind an `AsyncStream<VADEvent>`.
3. `VoiceSocket.swift` opens `/ws/voice`, sends `client_hello`, and sends completed VAD utterances as 16 kHz mono WAV.
4. `VADTestView` shows the current speaking/silent state, socket state, transcript, assistant text, and recent events.
5. The app bundles `silero_vad.onnx`.
6. Background audio is declared in `Info.plist`.

## sherpa-onnx assets

Vendored assets are under:

1. `HermesVoice/Vendor/sherpa-onnx/`
2. `HermesVoice/Vendor/sherpa-onnx-swift/`

See:

1. `HermesVoice/Vendor/sherpa-onnx/UPSTREAM.md`

## Build

From this repository root:

```bash
xcodebuild -project mobile/ios/HermesVoice/HermesVoice.xcodeproj -scheme HermesVoice -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Physical iPhone VAD behavior must still be verified on device before closing the mobile VAD phase.
