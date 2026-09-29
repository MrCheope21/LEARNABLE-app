import Foundation

/// AI curriculum proposals (docs/API.md "AI curriculum generation").
struct RemoteCurriculumRepository: CurriculumRepository {
    let apiClient: APIClient

    func generateProposal(courseId: UUID, chapterId: UUID?) async throws -> CurriculumProposal {
        try await apiClient.post(
            "/api/v1/courses/\(courseId.uuidString)/curriculum-proposals",
            body: GenerateBody(chapterId: chapterId)
        )
    }

    func fetchProposal(id: UUID) async throws -> CurriculumProposal {
        try await apiClient.get("/api/v1/curriculum-proposals/\(id.uuidString)")
    }

    func applyProposal(id: UUID, body: CurriculumApplyBody) async throws -> [ChapterNode] {
        try await apiClient.post(
            "/api/v1/curriculum-proposals/\(id.uuidString)/apply", body: body
        )
    }

    func rejectProposal(id: UUID) async throws {
        try await apiClient.delete("/api/v1/curriculum-proposals/\(id.uuidString)")
    }
}

private struct GenerateBody: Encodable {
    let chapterId: UUID?
}
