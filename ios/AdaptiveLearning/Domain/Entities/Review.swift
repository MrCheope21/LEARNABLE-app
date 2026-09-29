import Foundation

/// What a study session is for (docs/SCHEDULING.md §4). The backend decides what each may change;
/// the app never computes memory levels or due dates.
enum SessionIntent: String, ResilientEnum {
    case learn = "LEARN"
    case scheduledReview = "SCHEDULED_REVIEW"
    case practice = "PRACTICE"
    case exam = "EXAM"
    case unknown
}

enum SelectionMode: String, ResilientEnum {
    case new = "NEW"
    case due = "DUE"
    case courseOrder = "COURSE_ORDER"
    case random = "RANDOM"
    case weak = "WEAK"
    case recentlyFailed = "RECENTLY_FAILED"
    case markedHard = "MARKED_HARD"
    case selected = "SELECTED"
    case unknown
}

/// docs/PROJECT_SPEC.md §46. Decided by the backend's resolver or by the user; never by the AI.
enum ReviewOutcome: String, ResilientEnum {
    case again = "AGAIN"
    case hard = "HARD"
    case good = "GOOD"
    case easy = "EASY"
    case unknown

    /// The grades a user can give themselves, in order.
    static let userGrades: [ReviewOutcome] = [.again, .hard, .good, .easy]
}

struct ReviewSession: Identifiable, Codable, Equatable {
    let id: UUID
    let courseId: UUID
    var intent: SessionIntent
    var selectionMode: SelectionMode
    /// Whether answers in this session move the schedule (PRACTICE: no, unless opted in).
    var affectsSchedule: Bool
    var total: Int
    var position: Int
    var startedAt: Date
    var endedAt: Date?
}

/// `POST /courses/{id}/review-sessions` body.
struct SessionRequest: Encodable, Equatable {
    var intent: SessionIntent
    var selectionMode: SelectionMode?
    var conceptIds: [UUID]?
    var limit: Int = 20
    var updateSchedule: Bool = false

    static func learn(conceptIds: [UUID]? = nil) -> SessionRequest {
        SessionRequest(intent: .learn, selectionMode: nil, conceptIds: conceptIds)
    }

    static let scheduledReview = SessionRequest(intent: .scheduledReview, selectionMode: nil)
    static let practiceHard = SessionRequest(intent: .practice, selectionMode: .markedHard)
}

struct SessionCard: Codable, Equatable {
    var session: ReviewSession
    var done: Bool
    var card: StudyCard?
}

struct StudyCard: Codable, Equatable {
    let learningItemId: UUID
    let conceptId: UUID
    var conceptTitle: String
    var question: CardQuestion
    /// LEARN only: what to encode, shown before the first retrieval.
    var introduction: Introduction?
    /// An earlier answer to this card that still has no outcome.
    var pendingAnswerId: UUID?
}

struct CardQuestion: Codable, Equatable {
    let id: UUID
    var questionType: QuestionType
    var text: String
}

struct Introduction: Codable, Equatable {
    var title: String
    var objective: String
    var expectedKnowledge: String
    var essentialPoints: [String]
    var sources: [SourceReference]
}

struct AnswerRequest: Encodable, Equatable {
    var questionFormulationId: UUID
    var text: String
    var method = "TEXT"
}

struct OverrideRequest: Encodable, Equatable {
    var outcome: ReviewOutcome
    var note: String?
}

/// The backend's full verdict on one answer (docs/API.md "Answering").
struct AnswerResult: Codable, Equatable {
    let answerId: UUID
    let learningItemId: UUID
    let questionFormulationId: UUID
    var intent: SessionIntent
    var text: String
    /// The latest AI evaluation attempt, kept as the AI wrote it.
    var evaluation: Evaluation?
    /// What the backend's rules made of the evaluation; nil when it couldn't decide.
    var resolvedOutcome: ReviewOutcome?
    /// The user's own grade, if they gave one.
    var overrideOutcome: ReviewOutcome?
    var finalOutcome: ReviewOutcome?
    /// No outcome yet: retry the evaluation or grade it yourself.
    var needsSelfGrade: Bool
    /// Null when the answer didn't move the schedule.
    var schedule: ScheduleChange?
    var reference: Reference
    var session: ReviewSession
}

struct Evaluation: Codable, Equatable {
    let id: UUID
    var status: EvaluationStatus
    var errorMessage: String?
    var classification: EvaluationClassification?
    var correctness: Double?
    var completeness: Double?
    var conceptualUnderstanding: Double?
    var precision: Double?
    var confidence: Double?
    var correctPoints: [String]
    var missingPoints: [String]
    var misconceptions: [String]
    var sourceCorrections: [String]
    var contextSufficient: Bool?
    var feedback: String
}

enum EvaluationStatus: String, ResilientEnum {
    case completed = "COMPLETED"
    case failed = "FAILED"
    case notConfigured = "NOT_CONFIGURED"
    case unknown
}

enum EvaluationClassification: String, ResilientEnum {
    case correct = "CORRECT"
    case partiallyCorrect = "PARTIALLY_CORRECT"
    case misconception = "MISCONCEPTION"
    case wrong = "WRONG"
    case uncertain = "UNCERTAIN"
    case unknown
}

struct ScheduleChange: Codable, Equatable {
    var previousState: MemoryState
    var previousLevel: Int
    var previousDueAt: Date?
    var nextState: MemoryState
    var nextLevel: Int
    var nextDueAt: Date?
    var latenessSeconds: Int
}

/// The correct answer and its sources, shown with the feedback.
struct Reference: Codable, Equatable {
    var expectedKnowledge: String
    var essentialPoints: [String]
    var sources: [SourceReference]
}
