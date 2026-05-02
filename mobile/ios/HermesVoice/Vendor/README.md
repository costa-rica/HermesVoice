# iOS vendor runtime

HermesVoice uses sherpa-onnx only for on-device VAD. STT, assistant response, and TTS remain backend-driven.

1. The native runtime folder is intentionally ignored by Git:
   - `mobile/ios/HermesVoice/Vendor/sherpa-onnx/`

2. The ignored folder contains large binary artifacts that exceed GitHub file limits:
   - `sherpa-onnx.xcframework`
   - `ios-onnxruntime/onnxruntime.xcframework`

3. Upstream context:
   - Repository: `https://github.com/k2-fsa/sherpa-onnx`
   - Tested commit: `c66915948334df49be21db186199e6ddfc13fec0`
   - Release archive: `sherpa-onnx-v1.13.0-ios-no-tts.tar.bz2`
   - Archive SHA-256: `316cc0712d2cd7c6ff9bc49d6e7b75c9f65c5ddf78edb075344c0642cfb48d13`

4. Tracked files that remain in this repo:
   - `Vendor/sherpa-onnx-swift/SherpaOnnx.swift`
   - `Vendor/sherpa-onnx-swift/SherpaOnnx-Bridging-Header.h`
   - `HermesVoice/silero_vad.onnx`

