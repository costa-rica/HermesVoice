# HermesVoice iOS

The native iOS app uses the public HermesVoice backend origin by default:

- API origin: `https://hermes-voice.dashanddata.com`
- Voice WebSocket: `wss://hermes-voice.dashanddata.com/ws/voice`

Debug builds expose a Settings screen where you can temporarily override the
backend origin for development. Release builds always use the public HTTPS
origin and derive the WebSocket URL from that same base.
