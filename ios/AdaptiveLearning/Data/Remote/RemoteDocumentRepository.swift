import Foundation

/// Knowledge Repository endpoints (docs/API.md "Knowledge Repository / documents").
struct RemoteDocumentRepository: DocumentRepository {
    let apiClient: APIClient

    func fetchDocuments(courseId: UUID, chapterId: UUID?) async throws -> [CourseDocument] {
        var query: [URLQueryItem] = []
        if let chapterId {
            query.append(URLQueryItem(name: "chapter_id", value: chapterId.uuidString))
        }
        return try await apiClient.get(
            "/api/v1/courses/\(courseId.uuidString)/documents", query: query
        )
    }

    func uploadDocument(
        courseId: UUID, chapterId: UUID?, fileName: String, data: Data
    ) async throws -> CourseDocument {
        var fields: [String: String] = [:]
        if let chapterId {
            fields["chapter_id"] = chapterId.uuidString
        }
        return try await apiClient.upload(
            "/api/v1/courses/\(courseId.uuidString)/documents",
            fileName: fileName,
            data: data,
            fields: fields
        )
    }

    func deleteDocument(id: UUID) async throws {
        try await apiClient.delete("/api/v1/documents/\(id.uuidString)")
    }

    func fetchPassages(documentId: UUID, offset: Int, limit: Int) async throws -> [SourcePassage] {
        try await apiClient.get(
            "/api/v1/documents/\(documentId.uuidString)/chunks",
            query: [
                URLQueryItem(name: "offset", value: String(offset)),
                URLQueryItem(name: "limit", value: String(limit)),
            ]
        )
    }

    func fetchPassage(documentId: UUID, passageId: UUID) async throws -> SourcePassage {
        try await apiClient.get(
            "/api/v1/documents/\(documentId.uuidString)/chunks/\(passageId.uuidString)"
        )
    }
}
