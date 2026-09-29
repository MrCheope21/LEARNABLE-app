import Foundation

/// Study sessions and answers (docs/API.md "Review sessions"). The backend evaluates, resolves
/// the outcome and schedules; this only carries requests and results.
struct RemoteReviewRepository: ReviewRepository {
    let apiClient: APIClient

    func startSession(courseId: UUID, request: SessionRequest) async throws -> ReviewSession {
        try await apiClient.post(
            "/api/v1/courses/\(courseId.uuidString)/review-sessions", body: request
        )
    }

    func nextCard(sessionId: UUID) async throws -> SessionCard {
        try await apiClient.get("/api/v1/review-sessions/\(sessionId.uuidString)/next")
    }

    func submitAnswer(
        sessionId: UUID, questionId: UUID, text: String
    ) async throws -> AnswerResult {
        try await apiClient.post(
            "/api/v1/review-sessions/\(sessionId.uuidString)/answers",
            body: AnswerRequest(questionFormulationId: questionId, text: text)
        )
    }

    func fetchAnswer(id: UUID) async throws -> AnswerResult {
        try await apiClient.get("/api/v1/answers/\(id.uuidString)")
    }

    func retryEvaluation(answerId: UUID) async throws -> AnswerResult {
        try await apiClient.post("/api/v1/answers/\(answerId.uuidString)/evaluate")
    }

    func override(answerId: UUID, outcome: ReviewOutcome) async throws -> AnswerResult {
        try await apiClient.post(
            "/api/v1/answers/\(answerId.uuidString)/override",
            body: OverrideRequest(outcome: outcome)
        )
    }

    func skip(sessionId: UUID) async throws -> SessionCard {
        try await apiClient.post("/api/v1/review-sessions/\(sessionId.uuidString)/skip")
    }

    func endSession(sessionId: UUID) async throws {
        let _: ReviewSession = try await apiClient.post(
            "/api/v1/review-sessions/\(sessionId.uuidString)/end"
        )
    }
}
