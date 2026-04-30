import AVFoundation
import OSLog

private let log = Logger(subsystem: "com.dashanddata.HermesVoice", category: "AudioSessionManager")

struct AudioSessionManager {

    // Call once before starting the engine. Idempotent — safe to call on every PTT press.
    static func configureForVoice() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(
            .playAndRecord,
            mode: .voiceChat,
            options: [.allowBluetooth, .allowBluetoothA2DP, .defaultToSpeaker]
        )
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        log.debug("AVAudioSession activated: playAndRecord/voiceChat")
    }

    // Returns true when the user has (or just granted) microphone access.
    // Must be called before installing a tap on iOS 17+.
    static func requestMicPermission() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted:
            return true
        case .undetermined:
            let granted = await AVAudioApplication.requestRecordPermission()
            log.info("Microphone permission requested — granted=\(granted)")
            return granted
        case .denied:
            log.warning("Microphone permission denied")
            return false
        @unknown default:
            return false
        }
    }

    static func deactivate() {
        try? AVAudioSession.sharedInstance().setActive(
            false, options: .notifyOthersOnDeactivation
        )
        log.debug("AVAudioSession deactivated")
    }
}
