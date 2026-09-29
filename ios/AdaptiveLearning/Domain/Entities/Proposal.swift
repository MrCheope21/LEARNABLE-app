import Foundation

/// An AI-proposed curriculum awaiting the user's review (docs/API.md "AI curriculum
/// generation"). Nothing reaches the Course until the user applies it.
struct CurriculumProposal: Identifiable, Codable, Equatable {
    let id: UUID
    let courseId: UUID
    /// Set: Topics → Concepts for this Chapter (`topics`). Null: a whole-Course proposal
    /// (`chapters`).
    let chapterId: UUID?
    var status: ProposalStatus
    var errorMessage: String?
    var chapters: [ProposedChapter]?
    var topics: [ProposedTopic]?
    var passagesUsed: Int
    var passagesTotal: Int
    var droppedConcepts: Int
}

enum ProposalStatus: String, ResilientEnum {
    case generating = "GENERATING"
    case ready = "READY"
    case insufficientContext = "INSUFFICIENT_CONTEXT"
    case failed = "FAILED"
    case applied = "APPLIED"
    case unknown
}

struct ProposedChapter: Codable, Equatable {
    var title: String
    var description: String
    var topics: [ProposedTopic]
}

struct ProposedTopic: Codable, Equatable {
    var title: String
    var description: String
    /// The concepts go into this existing Topic.
    var existingTopicId: UUID?
    var concepts: [ProposedConcept]
}

struct ProposedConcept: Codable, Equatable {
    var title: String
    var description: String
    /// The new material also teaches this existing Concept: applying links it, no duplicate.
    var existingConceptId: UUID?
    var sources: [SourceReference]
}

/// `POST /curriculum-proposals/{id}/apply` body: exactly one of `chapters` / `topics`.
struct CurriculumApplyBody: Encodable, Equatable {
    var chapters: [ApplyChapter]?
    var topics: [ApplyTopic]?
}

struct ApplyChapter: Encodable, Equatable {
    var title: String
    var description: String
    var topics: [ApplyTopic]
}

struct ApplyTopic: Encodable, Equatable {
    var title: String
    var description: String
    var existingTopicId: UUID?
    var concepts: [ApplyConcept]
}

struct ApplyConcept: Encodable, Equatable {
    var title: String
    var description: String
    var existingConceptId: UUID?
    var sourceChunkIds: [UUID]
}
