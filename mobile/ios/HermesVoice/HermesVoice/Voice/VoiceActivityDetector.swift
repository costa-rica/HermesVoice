import Foundation

/// Energy-based voice activity detector.
///
/// Call `process(level:)` with the RMS of each audio buffer (~85 ms chunks
/// at 48 kHz hardware rate). Fires `onSpeechStarted` after consecutive
/// above-threshold buffers reach `onsetCount`, and `onSpeechEnded` after
/// consecutive below-threshold buffers reach `offsetCount`.
///
/// All callbacks fire on whichever thread `process` is called from —
/// callers are responsible for dispatching to the main actor if needed.
final class VoiceActivityDetector {

    // MARK: - Tunable thresholds

    /// RMS level (0–1) above which audio is considered speech.
    var speechThreshold: Float = 0.015
    /// Consecutive above-threshold chunks required to declare speech onset.
    var onsetCount: Int = 3   // ~250 ms
    /// Consecutive below-threshold chunks required to declare speech end.
    var offsetCount: Int = 10  // ~850 ms

    // MARK: - Callbacks

    var onSpeechStarted: (() -> Void)?
    var onSpeechEnded: (() -> Void)?

    // MARK: - State

    private(set) var isSpeaking = false
    private var consecutiveAbove = 0
    private var consecutiveBelow = 0

    // MARK: - API

    func process(level: Float) {
        if level >= speechThreshold {
            consecutiveAbove += 1
            consecutiveBelow = 0
            if !isSpeaking, consecutiveAbove >= onsetCount {
                isSpeaking = true
                onSpeechStarted?()
            }
        } else {
            consecutiveBelow += 1
            consecutiveAbove = 0
            if isSpeaking, consecutiveBelow >= offsetCount {
                isSpeaking = false
                onSpeechEnded?()
            }
        }
    }

    func reset() {
        consecutiveAbove = 0
        consecutiveBelow = 0
        isSpeaking = false
    }
}
