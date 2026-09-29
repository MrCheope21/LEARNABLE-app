import Foundation

// Course → Chapter → Topic → Concept, as `GET /api/v1/courses/{id}/outline` returns it
// (docs/API.md "Curriculum").

struct ChapterNode: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let courseId: UUID
    var title: String
    var description: String
    var order: Int
    var paused: Bool
    var topics: [TopicNode]
}

struct TopicNode: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let chapterId: UUID
    let courseId: UUID
    var title: String
    var description: String
    var order: Int
    var paused: Bool
    var concepts: [Concept]
}

/// Basic conceptual knowledge unit — NOT a flashcard (docs/PROJECT_SPEC.md §15). It has no memory
/// state of its own; its Learning Items do.
struct Concept: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let topicId: UUID
    let chapterId: UUID
    let courseId: UUID
    var title: String
    var description: String
    var order: Int
    var studyState: StudyState
    /// ACTIVE and not inside a paused Topic/Chapter/Course.
    var isReviewable: Bool
    /// Its source material was deleted and nothing supports it any more.
    var needsSourceReview: Bool
    var itemGenerationStatus: ItemGenerationStatus
    /// Why generation failed, safe to show.
    var itemGenerationError: String?
}

/// docs/PROJECT_SPEC.md §22 — does NOT represent memory strength.
enum StudyState: String, ResilientEnum {
    case notStudied = "NOT_STUDIED"
    case studied = "STUDIED"
    case active = "ACTIVE"
    case paused = "PAUSED"
    case completed = "COMPLETED"
    case unknown
}

enum ItemGenerationStatus: String, ResilientEnum {
    case notStarted = "NONE"
    case generating = "GENERATING"
    case ready = "READY"
    case insufficientContext = "INSUFFICIENT_CONTEXT"
    case failed = "FAILED"
    case unknown
}

/// Concept study-state actions (`POST /api/v1/concepts/{id}/<action>`, docs/API.md).
enum ConceptAction: String {
    case markStudied = "mark-studied"
    case activate
    case pause
    case resume
    case deactivate
    case complete
}

/// Where a passage comes from (docs/API.md: the same shape everywhere a source is referenced).
struct SourceReference: Codable, Equatable, Hashable {
    let chunkId: UUID
    let documentId: UUID
    var documentName: String
    var pageNumber: Int?
    var section: String?
}

extension SourceReference: Identifiable {
    var id: UUID { chunkId }
}
