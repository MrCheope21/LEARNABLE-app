import Foundation

/// Abstraction over speech-to-text so the review engine never hard-codes a specific transcription
/// backend (docs/PROJECT_SPEC.md §31). Concrete implementations: AppleSpeechTranscriptionService
/// today; alternative/on-device providers can be swapped in later without touching Review code.
protocol SpeechTranscriptionService {
    func startRecording() async throws
    func stopRecording() async throws -> String
}
