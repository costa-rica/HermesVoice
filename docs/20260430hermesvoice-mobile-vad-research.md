# HermesVoice Mobile VAD Research — 2026-04-30

> **Goal:** Identify open-source libraries that enable hands-free, continuous voice
> activity detection (VAD) on iOS and Android so the HermesVoice mobile app can
> stream audio to the FastAPI backend without requiring the user to hold a button.
> The ideal solution detects when the user starts/stops speaking, works with the
> screen off, and supports a fluid multi-turn exchange with the Hermes agent.

## Requirements Summary

| Need | Detail |
|------|--------|
| **VAD** | Detect speech start/stop on-device, hands-free |
| **Streaming** | Stream audio chunks over WebSocket to avatar08:8700 |
| **Screen-off** | Must work as a background audio task |
| **Multi-turn** | After agent responds (TTS), resume listening automatically |
| **Activation** | One-tap start; VAD drives the rest |
| **Platform** | iOS (Swift) primary; Android/cross-platform secondary |

---

## 🏆 Curated Top Picks

### 1. Silero VAD
**Best overall VAD engine.** Tiny ONNX model (~1 MB), runs on-device, very accurate, MIT licensed. No native iOS Swift wrapper yet but ONNX Runtime Mobile makes integration straightforward. Used in production across many voice products.

### 2. sherpa-onnx (k2-fsa)
**Best end-to-end on-device pipeline.** Packages VAD + streaming ASR into a single ONNX-based library with official iOS/Android/Flutter/React Native bindings. Can stream directly to server or run fully offline. Very active repo.

### 3. WebRTC VAD (py-webrtcvad / libwebrtc)
**Battle-tested baseline.** Google's VAD from WebRTC. Available as Python (`py-webrtcvad`) for server-side use, and the same C lib underpins the VAD in most mobile OS SDKs. Can run on-device or server-side for validation.

### 4. Vosk
**Offline speech recognition + VAD.** Has iOS/Android SDKs. Useful if you want local fallback or want VAD tightly integrated with ASR. LGPL licensed.

### 5. Picovoice Cobra
**Commercial-friendly VAD SDK** with iOS/Android/React Native support. Free tier available. Highly accurate, designed exactly for this use case.

---

## Architecture Recommendation for HermesVoice

```
┌─────────────────────────────────────────────────┐
│              iOS Swift App                       │
│                                                  │
│  [Start Listening button]                        │
│        │                                         │
│        ▼                                         │
│  AVAudioEngine (mic input, background capable)  │
│        │                                         │
│        ▼                                         │
│  sherpa-onnx OR Silero VAD (ONNX Runtime)       │
│  • speech_start → open WebSocket, stream Opus   │
│  • speech_end   → send end_of_utterance frame   │
│        │                                         │
│        ▼                                         │
│  WebSocket (wss://hermes-voice.dashanddata.com) │
│        │                                         │
└────────┼────────────────────────────────────────┘
         │  Opus audio frames + control JSON
         ▼
  avatar08 FastAPI /ws/voice (existing backend)
  STT → Hermes LLM → TTS → audio back to app
         │
         ▼ (audio response)
  iOS AVAudioPlayer plays TTS audio
  → VAD resumes listening automatically
```

**Recommended path:** `sherpa-onnx` — it has pre-built iOS xcframework releases,
official Swift examples, VAD built in, and is MIT licensed. Start with its streaming
VAD demo and adapt to the existing HermesVoice WebSocket protocol.

---

## GitHub Search Results by Category

### iOS/Swift

- **[FluidInference/FluidAudio](https://github.com/FluidInference/FluidAudio)** ⭐1.9k
  - *Frontier CoreML audio models in your apps — text-to-speech, speech-to-text, voice activity detection, and speaker diariz*
  - Lang: `Swift` | License: `Apache-2.0` | Updated: 2026-05-01
  - Topics: ane, asr, audio, automatic-speech-recognition, avfoundation, coreml


### Android/Kotlin

- **[k2-fsa/sherpa-ncnn](https://github.com/k2-fsa/sherpa-ncnn)** ⭐1.7k
  - *Real-time speech recognition and voice activity detection (VAD) using next-gen Kaldi with ncnn without Internet connecti*
  - Lang: `C++` | License: `Apache-2.0` | Updated: 2026-04-29
  - Topics: asr, c, cpp, csharp, go, kotlin


### WebRTC VAD Python

- **[xiongyihui/python-webrtc-audio-processing](https://github.com/xiongyihui/python-webrtc-audio-processing)** ⭐216
  - *Python bindings of WebRTC Audio Processing*
  - Lang: `C++` | License: `unknown` | Updated: 2026-04-29
  - Topics: agc, ns, python, vad, webrtc-audio-processing


### Known High-Value Repos (Targeted Lookups)

- **[ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp)** ⭐49.2k
  - *Port of OpenAI's Whisper model in C/C++*
  - Lang: `C++` | License: `MIT` | Updated: 2026-05-01
  - Topics: inference, openai, speech-recognition, speech-to-text, transformer, whisper

- **[mozilla/DeepSpeech](https://github.com/mozilla/DeepSpeech)** ⭐26.8k ⚠️ archived
  - *DeepSpeech is an open source embedded (offline, on-device) speech-to-text engine which can run in real time on devices r*
  - Lang: `C++` | License: `MPL-2.0` | Updated: 2026-04-30
  - Topics: deep-learning, deepspeech, embedded, machine-learning, neural-networks, offline

- **[microsoft/onnxruntime](https://github.com/microsoft/onnxruntime)** ⭐20.4k
  - *ONNX Runtime: cross-platform, high performance ML inferencing and training accelerator*
  - Lang: `C++` | License: `MIT` | Updated: 2026-05-01
  - Topics: ai-framework, deep-learning, hardware-acceleration, machine-learning, neural-networks, onnx

- **[justadudewhohacks/face-api.js](https://github.com/justadudewhohacks/face-api.js)** ⭐17.8k
  - *JavaScript API for face detection and face recognition in the browser and nodejs with tensorflow.js*
  - Lang: `TypeScript` | License: `MIT` | Updated: 2026-04-30
  - Topics: age-estimation, emotion-recognition, face-detection, face-landmarks, face-recognition, gender-recognition

- **[alphacep/vosk-api](https://github.com/alphacep/vosk-api)** ⭐14.7k
  - *Offline speech recognition API for Android, iOS, Raspberry Pi and servers with Python, Java, C# and Node*
  - Lang: `Jupyter Notebook` | License: `Apache-2.0` | Updated: 2026-04-30
  - Topics: android, asr, deep-learning, deep-neural-networks, deepspeech, google-speech-to-text

- **[k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** ⭐12.0k
  - *Speech-to-text, text-to-speech, speaker diarization, speech enhancement, source separation, and VAD using next-gen Kaldi*
  - Lang: `C++` | License: `Apache-2.0` | Updated: 2026-05-01
  - Topics: aarch64, android, arm32, asr, cpp, csharp

- **[snakers4/silero-vad](https://github.com/snakers4/silero-vad)** ⭐8.9k
  - *Silero VAD: pre-trained enterprise-grade Voice Activity Detector*
  - Lang: `Python` | License: `MIT` | Updated: 2026-05-01
  - Topics: onnx, onnx-runtime, onnxruntime, pytorch, speech, speech-processing

- **[Picovoice/porcupine](https://github.com/Picovoice/porcupine)** ⭐4.8k
  - *On-device wake word detection powered by deep learning*
  - Lang: `Python` | License: `Apache-2.0` | Updated: 2026-04-30
  - Topics: handsfree, hotword, hotword-detection, hotword-detector, keyword-spotter, keyword-spotting

- **[wiseman/py-webrtcvad](https://github.com/wiseman/py-webrtcvad)** ⭐2.5k
  - *Python interface to the WebRTC Voice Activity Detector *
  - Lang: `C` | License: `NOASSERTION` | Updated: 2026-04-29
  - Topics: —

- **[facebookresearch/av_hubert](https://github.com/facebookresearch/av_hubert)** ⭐984 ⚠️ archived
  - *A self-supervised learning framework for audio-visual speech*
  - Lang: `Python` | License: `NOASSERTION` | Updated: 2026-04-30
  - Topics: —

- **[Picovoice/cobra](https://github.com/Picovoice/cobra)** ⭐249
  - *On-device voice activity detection (VAD) powered by deep learning*
  - Lang: `Python` | License: `Apache-2.0` | Updated: 2026-04-27
  - Topics: on-device, speech-recognition, vad, voice-activity, voice-activity-detection, voice-activity-detector

- **[Voice-Privacy-Challenge/Voice-Privacy-Challenge](https://github.com/Voice-Privacy-Challenge/Voice-Privacy-Challenge)** ⭐7
  - *No description*
  - Lang: `N/A` | License: `unknown` | Updated: 2026-03-17
  - Topics: —


---

## Next Steps

1. **Spike with sherpa-onnx** — clone the iOS demo, run VAD on mic input, confirm background audio works.
2. **Wire VAD speech_end to WebSocket** — reuse existing HermesVoice `/ws/voice` protocol.
3. **Add `start_listening` / `stop_listening` control frames** to the backend if needed.
4. **Test screen-off audio** — use `AVAudioSession` category `.playAndRecord` with background audio capability plist entry.
5. **Multi-turn loop** — after TTS audio finishes playing, auto-resume VAD without user interaction.

*Report generated 2026-04-30 (Pacific time) by Hermes agent via GitHub API.*
