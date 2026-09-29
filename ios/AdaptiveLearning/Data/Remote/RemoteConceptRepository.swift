import Foundation

/// Concepts and their Learning Items (docs/API.md "Concept study state", "Learning Items").
struct RemoteConceptRepository: ConceptRepository {
    let apiClient: APIClient

    func fetchConcept(id: UUID) async throws -> Concept {
        try await apiClient.get("/api/v1/concepts/\(id.uuidString)")
    }

    func perform(_ action: ConceptAction, conceptId: UUID) async throws -> Concept {
        try await apiClient.post("/api/v1/concepts/\(conceptId.uuidString)/\(action.rawValue)")
    }

    func fetchLearningItems(conceptId: UUID) async throws -> [LearningItem] {
        try await apiClient.get("/api/v1/concepts/\(conceptId.uuidString)/learning-items")
    }

    func generateLearningItems(conceptId: UUID) async throws -> Concept {
        try await apiClient.post(
            "/api/v1/concepts/\(conceptId.uuidString)/learning-items/generate"
        )
    }

    func setInTraining(_ inTraining: Bool, itemId: UUID) async throws -> LearningItem {
        let action = inTraining ? "train" : "untrain"
        return try await apiClient.post("/api/v1/learning-items/\(itemId.uuidString)/\(action)")
    }

    func fetchItemSources(itemId: UUID) async throws -> [SourcePassage] {
        try await apiClient.get("/api/v1/learning-items/\(itemId.uuidString)/sources")
    }
}
