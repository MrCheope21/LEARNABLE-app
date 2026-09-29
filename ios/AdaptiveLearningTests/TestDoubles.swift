import Foundation
@testable import AdaptiveLearning

enum TestError: Error {
    case boom
}

/// Hands out queued results in order; the last one repeats. Lets a test script a sequence such
/// as "generating, generating, ready" for polling.
struct ResultQueue<Value> {
    var results: [Result<Value, Error>]
    private(set) var calls = 0

    init(_ results: [Result<Value, Error>]) {
        self.results = results
    }

    mutating func next() throws -> Value {
        precondition(!results.isEmpty, "No result scripted")
        let index = min(calls, results.count - 1)
        calls += 1
        return try results[index].get()
    }
}

final class FakeCourseRepository: CourseRepository {
    var fetchResult: Result<[Course], Error> = .success([])
    var createError: Error?
    var outline: Result<[ChapterNode], Error> = .success([])
    var createChapterError: Error?
    private(set) var createdDrafts: [CourseDraft] = []
    private(set) var createdChapters: [String] = []

    func fetchCourses() async throws -> [Course] {
        try fetchResult.get()
    }

    func createCourse(_ draft: CourseDraft) async throws -> Course {
        createdDrafts.append(draft)
        if let createError { throw createError }
        return Course(
            id: UUID(), title: draft.title, description: draft.description, language: draft.language
        )
    }

    func fetchOutline(courseId: UUID) async throws -> [ChapterNode] {
        try outline.get()
    }

    func createChapter(courseId: UUID, title: String) async throws {
        if let createChapterError { throw createChapterError }
        createdChapters.append(title)
    }
}

final class FakeConceptRepository: ConceptRepository {
    var concept: ResultQueue<Concept>
    var items: Result<[LearningItem], Error> = .success([])
    var actionResult: Result<Concept, Error>?
    var generateResult: Result<Concept, Error>?
    var sources: [SourcePassage] = []
    private(set) var actions: [ConceptAction] = []
    private(set) var itemFetches = 0

    init(concept: [Result<Concept, Error>]) {
        self.concept = ResultQueue(concept)
    }

    var conceptFetches: Int { concept.calls }

    func fetchConcept(id: UUID) async throws -> Concept {
        try concept.next()
    }

    func perform(_ action: ConceptAction, conceptId: UUID) async throws -> Concept {
        actions.append(action)
        if let actionResult { return try actionResult.get() }
        return try concept.next()
    }

    func fetchLearningItems(conceptId: UUID) async throws -> [LearningItem] {
        itemFetches += 1
        return try items.get()
    }

    func generateLearningItems(conceptId: UUID) async throws -> Concept {
        if let generateResult { return try generateResult.get() }
        return try concept.next()
    }

    func setInTraining(_ inTraining: Bool, itemId: UUID) async throws -> LearningItem {
        guard var item = try items.get().first(where: { $0.id == itemId }) else {
            throw TestError.boom
        }
        item.inTraining = inTraining
        return item
    }

    func fetchItemSources(itemId: UUID) async throws -> [SourcePassage] {
        sources
    }
}

final class FakeCurriculumRepository: CurriculumRepository {
    var generateResult: Result<CurriculumProposal, Error> = .failure(TestError.boom)
    var proposal: ResultQueue<CurriculumProposal> = ResultQueue([.failure(TestError.boom)])
    var applyError: Error?
    private(set) var appliedBodies: [CurriculumApplyBody] = []
    private(set) var rejectedIds: [UUID] = []
    private(set) var generatedFor: [UUID?] = []

    func generateProposal(courseId: UUID, chapterId: UUID?) async throws -> CurriculumProposal {
        generatedFor.append(chapterId)
        return try generateResult.get()
    }

    func fetchProposal(id: UUID) async throws -> CurriculumProposal {
        try proposal.next()
    }

    func applyProposal(id: UUID, body: CurriculumApplyBody) async throws -> [ChapterNode] {
        appliedBodies.append(body)
        if let applyError { throw applyError }
        return []
    }

    func rejectProposal(id: UUID) async throws {
        rejectedIds.append(id)
    }
}

final class FakeReviewRepository: ReviewRepository {
    var startResult: Result<ReviewSession, Error> = .failure(TestError.boom)
    var cards: ResultQueue<SessionCard> = ResultQueue([.failure(TestError.boom)])
    var submitResult: Result<AnswerResult, Error> = .failure(TestError.boom)
    var answer: Result<AnswerResult, Error> = .failure(TestError.boom)
    var retryResult: Result<AnswerResult, Error> = .failure(TestError.boom)
    var overrideResult: Result<AnswerResult, Error> = .failure(TestError.boom)
    private(set) var startedRequests: [SessionRequest] = []
    private(set) var submittedTexts: [String] = []
    private(set) var overrides: [ReviewOutcome] = []
    private(set) var skips = 0
    private(set) var ended: [UUID] = []

    func startSession(courseId: UUID, request: SessionRequest) async throws -> ReviewSession {
        startedRequests.append(request)
        return try startResult.get()
    }

    func nextCard(sessionId: UUID) async throws -> SessionCard {
        try cards.next()
    }

    func submitAnswer(sessionId: UUID, questionId: UUID, text: String) async throws -> AnswerResult {
        submittedTexts.append(text)
        return try submitResult.get()
    }

    func fetchAnswer(id: UUID) async throws -> AnswerResult {
        try answer.get()
    }

    func retryEvaluation(answerId: UUID) async throws -> AnswerResult {
        try retryResult.get()
    }

    func override(answerId: UUID, outcome: ReviewOutcome) async throws -> AnswerResult {
        overrides.append(outcome)
        return try overrideResult.get()
    }

    func skip(sessionId: UUID) async throws -> SessionCard {
        skips += 1
        return try cards.next()
    }

    func endSession(sessionId: UUID) async throws {
        ended.append(sessionId)
    }
}

final class FakeProgressRepository: ProgressRepository {
    var home: Result<HomeSummary, Error> = .success(.empty)
    var progress: Result<CourseProgress, Error> = .failure(TestError.boom)
    var reviewLoad: Result<ReviewLoad, Error> = .success(.empty)
    private(set) var progressRequests: [UUID] = []

    func fetchHome() async throws -> HomeSummary {
        try home.get()
    }

    func fetchProgress(courseId: UUID) async throws -> CourseProgress {
        progressRequests.append(courseId)
        return try progress.get()
    }

    func fetchReviewLoad(courseId: UUID) async throws -> ReviewLoad {
        try reviewLoad.get()
    }
}

final class InMemoryAnswerDraftStore: AnswerDraftStore {
    private(set) var drafts: [String: String] = [:]

    func load(key: String) -> String? { drafts[key] }
    func save(_ text: String, key: String) { drafts[key] = text }
    func clear(key: String) { drafts[key] = nil }
}

final class FakeAuthRepository: AuthRepository {
    var error: Error?
    private(set) var signInCalls = 0
    private(set) var registerCalls = 0
    private(set) var signOutCalls = 0

    func signIn(email: String, password: String) async throws {
        signInCalls += 1
        if let error { throw error }
    }

    func register(email: String, password: String) async throws {
        registerCalls += 1
        if let error { throw error }
    }

    func signOut() {
        signOutCalls += 1
    }
}

final class FakeDocumentRepository: DocumentRepository {
    /// Successive results for fetchDocuments; the last one repeats.
    var documentResponses: [Result<[CourseDocument], Error>] = [.success([])]
    var uploadResult: Result<CourseDocument, Error>?
    var deleteError: Error?
    var passages: [SourcePassage] = []
    var passageResult: Result<SourcePassage, Error> = .failure(TestError.boom)
    private(set) var fetchCount = 0
    private(set) var fetchedChapterIds: [UUID?] = []
    private(set) var uploads: [(fileName: String, size: Int)] = []
    private(set) var uploadChapterIds: [UUID?] = []
    private(set) var deletedIds: [UUID] = []
    private(set) var passageRequests: [(offset: Int, limit: Int)] = []

    func fetchDocuments(courseId: UUID, chapterId: UUID?) async throws -> [CourseDocument] {
        fetchedChapterIds.append(chapterId)
        let index = min(fetchCount, documentResponses.count - 1)
        fetchCount += 1
        return try documentResponses[index].get()
    }

    func uploadDocument(
        courseId: UUID, chapterId: UUID?, fileName: String, data: Data
    ) async throws -> CourseDocument {
        uploads.append((fileName, data.count))
        uploadChapterIds.append(chapterId)
        if let uploadResult { return try uploadResult.get() }
        return .sample(filename: fileName, status: .processing)
    }

    func deleteDocument(id: UUID) async throws {
        if let deleteError { throw deleteError }
        deletedIds.append(id)
    }

    func fetchPassages(documentId: UUID, offset: Int, limit: Int) async throws -> [SourcePassage] {
        passageRequests.append((offset, limit))
        return Array(passages.dropFirst(offset).prefix(limit))
    }

    func fetchPassage(documentId: UUID, passageId: UUID) async throws -> SourcePassage {
        try passageResult.get()
    }
}

// MARK: - Samples (built from the captured backend responses where possible)

extension Course {
    static func sample(title: String = "Diritto Commerciale") -> Course {
        Course(id: UUID(), title: title, description: "", language: "it")
    }
}

extension Concept {
    static func sample(
        state: StudyState = .notStudied,
        generation: ItemGenerationStatus = .notStarted
    ) -> Concept {
        Concept(
            id: UUID(), topicId: UUID(), chapterId: UUID(), courseId: UUID(),
            title: "Il deposito bancario", description: "", order: 0,
            studyState: state, isReviewable: state == .active, needsSourceReview: false,
            itemGenerationStatus: generation, itemGenerationError: nil
        )
    }
}

extension CourseDocument {
    static func sample(
        id: UUID = UUID(),
        filename: String = "bilancio.pdf",
        status: DocumentStatus = .ready
    ) -> CourseDocument {
        CourseDocument(
            id: id,
            courseId: UUID(),
            filename: filename,
            kind: .pdf,
            sizeBytes: 1024,
            status: status,
            errorMessage: nil,
            pageCount: 3,
            chunkCount: 3,
            createdAt: Date()
        )
    }
}

extension SourcePassage {
    static func samples(count: Int, documentId: UUID = UUID()) -> [SourcePassage] {
        (0..<count).map { index in
            SourcePassage(
                id: UUID(),
                documentId: documentId,
                position: index,
                pageNumber: index + 1,
                section: "Capitolo",
                text: "Passaggio \(index)"
            )
        }
    }
}
