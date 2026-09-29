import Foundation

/// Wired up fully in Phase 14 (voice answering) using Apple's Speech framework. Present now so
/// the Speech layer boundary exists from the start (docs/PROJECT_SPEC.md §31) — the Review engine
/// depends only on the `SpeechTranscriptionService` protocol, never on this concrete type.
final class AppleSpeechTranscriptionService: SpeechTranscriptionService {
    func startRecording() async throws {
        throw SpeechServiceError.notYetImplemented
    }

    func stopRecording() async throws -> String {
        throw SpeechServiceError.notYetImplemented
    }
}

enum SpeechServiceError: Error {
    case notYetImplemented
}
