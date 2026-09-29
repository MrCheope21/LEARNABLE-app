import Foundation

/// The atomic unit that is trained and scheduled (docs/PROJECT_SPEC.md §25). Each has its own
/// memory state, shared by all of its question formulations (§26, §27). The app only ever shows
/// that state; the backend's SchedulingPolicy is the only thing that changes it.
struct LearningItem: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let conceptId: UUID
    let courseId: UUID
    var title: String
    var objective: String
    var expectedKnowledge: String
    var essentialPoints: [String]
    var role: LearningItemRole
    /// Whether it takes part in spaced repetition (the user's choice).
    var inTraining: Bool
    var difficulty: Int
    var order: Int
    var paused: Bool
    var reviewState: MemorySnapshot
    var questions: [QuestionFormulation]
}

enum LearningItemRole: String, ResilientEnum {
    case coreTrainable = "CORE_TRAINABLE"
    case supportingTrainable = "SUPPORTING_TRAINABLE"
    case commonTrap = "COMMON_TRAP"
    case informational = "INFORMATIONAL"
    case reference = "REFERENCE"
    case optionalExtension = "OPTIONAL_EXTENSION"
    case unknown
}

/// Read-only memory state (docs/API.md `review_state`).
struct MemorySnapshot: Codable, Equatable, Hashable {
    var state: MemoryState
    var level: Int
    var dueAt: Date?
    var lastReviewedAt: Date?
    var reviewCount: Int
    var successfulReviewCount: Int
    var failedReviewCount: Int
    var lapseCount: Int
    var hardCount: Int
    var markedHard: Bool
}

/// docs/PROJECT_SPEC.md §23
enum MemoryState: String, ResilientEnum {
    case new = "NEW"
    case learning = "LEARNING"
    case review = "REVIEW"
    case relearning = "RELEARNING"
    case mastered = "MASTERED"
    case unknown
}

struct QuestionFormulation: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    var questionType: QuestionType
    var text: String
    var timesAsked: Int
}

/// docs/PROJECT_SPEC.md §28
enum QuestionType: String, ResilientEnum {
    case recall = "RECALL"
    case definition = "DEFINITION"
    case explanation = "EXPLANATION"
    case whyHow = "WHY_HOW"
    case comparison = "COMPARISON"
    case causeEffect = "CAUSE_EFFECT"
    case application = "APPLICATION"
    case scenario = "SCENARIO"
    case calculation = "CALCULATION"
    case classification = "CLASSIFICATION"
    case teachBack = "TEACH_BACK"
    case oralExam = "ORAL_EXAM"
    case counterexample = "COUNTEREXAMPLE"
    case edgeCase = "EDGE_CASE"
    case conceptConnection = "CONCEPT_CONNECTION"
    case unknown
}
