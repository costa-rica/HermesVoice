# sherpa-onnx iOS VAD spike findings

Date: 2026-05-01

## 1. Result

- Result: partial pass, strong enough to proceed with HermesVoice native iOS planning with caveats.
- Core finding: sherpa-onnx Silero VAD can run on a physical iPhone using live microphone audio and reliably distinguish direct speech from silence and common non-speech noise in initial testing.
- Main caveat: Bluetooth headset microphone routing was not confirmed. Built-in iPhone microphone behavior is the validated path.
- Recommendation: proceed with HermesVoice vendoring/planning for built-in microphone VAD, but keep Bluetooth input support as a separate follow-up spike before treating headset input as supported.

This answers the Phase 0 foundation question for the built-in iPhone mic: sherpa-onnx VAD works on physical iPhone hardware and is suitable enough to continue HermesVoice mobile integration design. It should not yet be treated as a final production audio-routing implementation.

## 2. Environment

- Repository tested: `/Users/nick/Documents/sherpa-onnx`
- Downstream project: `/Users/nick/Documents/HermesVoice`
- Physical device seen by Xcode: `Leafy-outrider`
- iOS version reported by Xcode device list: `26.3.1`
- Device model: not recorded
- Xcode version: `Xcode 26.1`, build `17B55`
- Mac architecture: `arm64`
- sherpa-onnx commit: `c66915948334df49be21db186199e6ddfc13fec0`
- sherpa-onnx release archive used: `v1.13.0` no-TTS iOS archive

## 3. Assets used

- iOS framework archive:
  - Path: `/Users/nick/Documents/sherpa-onnx/downloads/sherpa-onnx-v1.13.0-ios-no-tts.tar.bz2`
  - Source: `https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.0/sherpa-onnx-v1.13.0-ios-no-tts.tar.bz2`
  - SHA-256: `316cc0712d2cd7c6ff9bc49d6e7b75c9f65c5ddf78edb075344c0642cfb48d13`
- Runtime framework paths installed for the spike:
  - `/Users/nick/Documents/sherpa-onnx/build-ios/sherpa-onnx.xcframework`
  - `/Users/nick/Documents/sherpa-onnx/build-ios/ios-onnxruntime/onnxruntime.xcframework`
- VAD model:
  - Path: `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx/silero_vad.onnx`
  - Source: `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx`
  - SHA-256: `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`

## 4. Spike target and files

- Xcode project:
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx.xcodeproj`
- Xcode scheme:
  - `SherpaOnnx`
- Modified files in the sherpa-onnx fork:
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx/SherpaOnnxViewModel.swift`
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx/ContentView.swift`
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx/Info.plist`
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx.xcodeproj/project.pbxproj`
- Added model resource:
  - `/Users/nick/Documents/sherpa-onnx/ios-swiftui/SherpaOnnx/SherpaOnnx/silero_vad.onnx`

The spike replaced the ASR-focused SwiftUI demo behavior with a minimal live microphone VAD UI. It shows `SPEAKING` or `SILENT` and logs speech start/end events to the Xcode console.

## 5. Build verification

- Simulator compile/link check:
  - Command used: `xcodebuild -project ios-swiftui/SherpaOnnx/SherpaOnnx.xcodeproj -scheme SherpaOnnx -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build`
  - Result: build succeeded
- Generic physical iOS arm64 compile/link check:
  - Command used: `xcodebuild -project ios-swiftui/SherpaOnnx/SherpaOnnx.xcodeproj -scheme SherpaOnnx -configuration Debug -sdk iphoneos -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build`
  - Result: build succeeded
- Physical device run:
  - Result: app launched and VAD behavior was manually tested on physical iPhone

## 6. VAD observations

- Microphone permission:
  - Permission was granted successfully.
- Speech start:
  - The app switched to `SPEAKING` when Nick talked directly into the iPhone microphone.
  - Example Xcode log:
    - `[HermesVoice VAD] Speech start at 3.17s`
    - `[HermesVoice VAD] Speech start at 7.46s`
- Speech end:
  - The app returned to non-speaking state after speech segments completed.
  - Example Xcode log:
    - `[HermesVoice VAD] Speech end at 4.19s, duration 1.34s`
    - `[HermesVoice VAD] Speech end at 8.77s, duration 1.63s`
- False positives:
  - User tested typing and other noise.
  - The app generally did not switch to `SPEAKING` for those non-speech noises.
  - The app primarily switched to `SPEAKING` when the user spoke directly into the microphone.
- False negatives:
  - No major false-negative issue was reported for direct speech into the iPhone microphone.
- Stability:
  - Short manual testing passed.
  - A formal 5-minute scripted stability run was not separately recorded.

## 7. Screen lock and background behavior

- Screen lock:
  - User reported that after shutting off the screen, talking still kept the app on `SPEAKING`.
  - This is a promising result for screen-off behavior.
- App background:
  - Full background behavior was not separately documented beyond the screen-off test.
- App configuration:
  - `UIBackgroundModes` includes `audio` in the spike `Info.plist`.
  - `AVAudioSession` is configured as `.playAndRecord`.

## 8. Bluetooth headset behavior

- Bluetooth headset microphone:
  - Not confirmed.
  - User reported not being able to talk to the app through Bluetooth headphones that normally work for phone calls.
- Interpretation:
  - This is expected or at least unsurprising for the current spike.
  - iOS Bluetooth audio routing can keep the built-in mic active unless the app explicitly manages route selection.
  - Phone-call style Bluetooth microphone input may require `.voiceChat` mode, route inspection, and potentially preferred input selection.
- Recommendation:
  - Treat Bluetooth headset mic support as a separate audio-routing spike.
  - Add route logging for `AVAudioSession.currentRoute.inputs` and `AVAudioSession.routeChangeNotification`.
  - Test `.voiceChat` mode vs `.measurement`.
  - Confirm whether the active input is built-in mic, Bluetooth HFP, or another route during headset testing.

## 9. Recommendation for HermesVoice

1. Proceed with HermesVoice native iOS integration planning using sherpa-onnx VAD for the built-in iPhone microphone.
2. Vendor only the minimal VAD pieces, not ASR, TTS, or full sherpa-onnx example behavior.
3. Keep the production app architecture backend-driven for STT, assistant response, and TTS as planned.
4. Add a HermesVoice-specific audio route layer before promising Bluetooth headset support.
5. Run one final 5-minute stability pass before closing the Phase 0 blocker completely.

## 10. Notes for vendoring

- Swift pieces worth studying or copying:
  - Live mic capture and 16 kHz mono conversion from `SherpaOnnxViewModel.swift`.
  - VAD setup using `sherpaOnnxSileroVadModelConfig`, `sherpaOnnxVadModelConfig`, and `SherpaOnnxVoiceActivityDetectorWrapper`.
  - Event handling using `isSpeechDetected()`, `front()`, `pop()`, and `reset()`.
- Native assets needed:
  - `sherpa-onnx.xcframework`
  - `onnxruntime.xcframework`
  - `silero_vad.onnx`
- Xcode setup quirk:
  - The app target needed an explicit `HEADER_SEARCH_PATHS` entry pointing to the sherpa-onnx xcframework headers for Xcode 26 bridging-header scanning.
- Current VAD parameters used:
  - Threshold: `0.5`
  - Minimum silence duration: `0.35`
  - Minimum speech duration: `0.25`
  - Window size: `512`
  - Maximum speech duration: `30.0`

## 11. Final assessment

- The spike is good enough to brief the HermesVoice coding agent.
- The HermesVoice blocker should be considered substantially de-risked for built-in iPhone microphone VAD.
- The blocker should not be marked fully resolved until the HermesVoice team decides whether Bluetooth headset input and formal 5-minute stability are required for Phase 0 completion.
