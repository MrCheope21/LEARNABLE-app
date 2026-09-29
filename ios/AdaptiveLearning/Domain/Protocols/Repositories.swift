import Foundation

// The boundary between the app and wherever data comes from. View models depend only on these
// protocols; concrete implementations are chosen once, in App/AppDependencies.swift, so tests
// substitute fakes without touching networking.

protocol AuthRepository {
    /// Exchanges credentials for an access token and stores it.
    func signIn(email: String, password: String) async throws
    /// Creates the account, then signs in.
    func register(email: String, password: String) async throws
    func signOut()
}

/// Fields for a new Course. Encoded as-is as the `POST /api/v1/courses` body (docs/API.md).
struct CourseDraft: Equatable, Encodable {
    var title: String
    var description: String
    var language: String
}

protocol CourseRepository {
    func fetchCourses() async throws -> [Course]
    func createCourse(_ draft: CourseDraft) async throws -> Course
    /// The whole tree: Chapters → Topics → Concepts.
    func fetchOutline(courseId: UUID) async throws -> [ChapterNode]
    func createChapter(courseId: UUID, title: String) async throws
}

protocol ConceptRepository {
    func fetchConcept(id: UUID) async throws -> Concept
    func perform(_ action: ConceptAction, conceptId: UUID) async throws -> Concept
    func fetchLearningItems(conceptId: UUID) async throws -> [LearningItem]
    /// Starts generation in the background; follow it with `fetchConcept`.
    func generateLearningItems(conceptId: UUID) async throws -> Concept
    func setInTraining(_ inTraining: Bool, itemId: UUID) async throws -> LearningItem
    /// The passages a Learning Item was generated from.
    func fetchItemSources(itemId: UUID) async throws -> [SourcePassage]
}

protocol CurriculumRepository {
    /// Starts generation (Chapter scope when `chapterId` is set); follow it with `fetchProposal`.
    func generateProposal(courseId: UUID, chapterId: UUID?) async throws -> CurriculumProposal
    func fetchProposal(id: UUID) async throws -> CurriculumProposal
    /// Returns the Course's outline after applying.
    func applyProposal(id: UUID, body: CurriculumApplyBody) async throws -> [ChapterNode]
    func rejectProposal(id: UUID) async throws
}

protocol ReviewRepository {
    func startSession(courseId: UUID, request: SessionRequest) async throws -> ReviewSession
    func nextCard(sessionId: UUID) async throws -> SessionCard
    func submitAnswer(
        sessionId: UUID, questionId: UUID, text: String
    ) async throws -> AnswerResult
    func fetchAnswer(id: UUID) async throws -> AnswerResult
    func retryEvaluation(answerId: UUID) async throws -> AnswerResult
    func override(answerId: UUID, outcome: ReviewOutcome) async throws -> AnswerResult
    func skip(sessionId: UUID) async throws -> SessionCard
    func endSession(sessionId: UUID) async throws
}

protocol ProgressRepository {
    func fetchHome() async throws -> HomeSummary
    func fetchProgress(courseId: UUID) async throws -> CourseProgress
    func fetchReviewLoad(courseId: UUID) async throws -> ReviewLoad
}

protocol DocumentRepository {
    /// `chapterId` lists only that Chapter's material.
    func fetchDocuments(courseId: UUID, chapterId: UUID?) async throws -> [CourseDocument]
    /// Uploads the file (filed under `chapterId` if set); the backend returns it as PROCESSING
    /// and finishes in the background.
    func uploadDocument(
        courseId: UUID, chapterId: UUID?, fileName: String, data: Data
    ) async throws -> CourseDocument
    func deleteDocument(id: UUID) async throws
    func fetchPassages(documentId: UUID, offset: Int, limit: Int) async throws -> [SourcePassage]
    /// One passage, for "View source".
    func fetchPassage(documentId: UUID, passageId: UUID) async throws -> SourcePassage
}

extension DocumentRepository {
    func fetchDocuments(courseId: UUID) async throws -> [CourseDocument] {
        try await fetchDocuments(courseId: courseId, chapterId: nil)
    }

    func uploadDocument(courseId: UUID, fileName: String, data: Data) async throws -> CourseDocument {
        try await uploadDocument(courseId: courseId, chapterId: nil, fileName: fileName, data: data)
    }
}

/// Keeps a typed answer until the backend has it (docs/PROJECT_SPEC.md §79: never lose an
/// answer). Survives the app being closed.
protocol AnswerDraftStore {
    func load(key: String) -> String?
    func save(_ text: String, key: String)
    func clear(key: String)
}
