import XCTest
@testable import AdaptiveLearning

/// The study loop against scripted backend responses (captured shapes, Fixtures.swift).
@MainActor
final class StudySessionViewModelTests: XCTestCase {
    private var repository: FakeReviewRepository!
    private var drafts: InMemoryAnswerDraftStore!

    override func setUp() async throws {
        repository = FakeReviewRepository()
        drafts = InMemoryAnswerDraftStore()
        repository.startResult = .success(try Fixtures.decode(ReviewSession.self, Fixtures.session))
        repository.cards = ResultQueue([
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardLearn)),
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardDone)),
        ])
        repository.submitResult = .success(try Fixtures.decode(AnswerResult.self, Fixtures.answerResult))
    }

    private func makeViewModel(_ request: SessionRequest = .learn()) -> StudySessionViewModel {
        StudySessionViewModel(
            courseId: UUID(), courseTitle: "Diritto bancario", request: request,
            repository: repository, drafts: drafts
        )
    }

    private func card() throws -> StudyCard {
        try XCTUnwrap(try Fixtures.decode(SessionCard.self, Fixtures.cardLearn).card)
    }

    func testLearnShowsTheIntroductionBeforeRecall() async throws {
        let viewModel = makeViewModel()

        await viewModel.start()

        XCTAssertEqual(repository.startedRequests.first?.intent, .learn)
        XCTAssertEqual(viewModel.phase, .introduction(try card()))
        viewModel.beginRecall()
        XCTAssertEqual(viewModel.phase, .answering(try card()))
    }

    func testSubmittingShowsTheBackendsResultAndClearsTheDraft() async throws {
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "  Il deposito bancario trasferisce la proprietà.  "

        await viewModel.submit()

        XCTAssertEqual(repository.submittedTexts, ["Il deposito bancario trasferisce la proprietà."])
        guard case .result(_, let result) = viewModel.phase else {
            return XCTFail("Expected a result, got \(viewModel.phase)")
        }
        XCTAssertEqual(result.finalOutcome, .good)
        XCTAssertEqual(viewModel.draft, "")
        XCTAssertTrue(drafts.drafts.isEmpty)
        XCTAssertEqual(viewModel.count(of: .good), 1)
    }

    func testFailedSubmissionKeepsTheAnswerInTheEditorAndOnDisk() async throws {
        repository.submitResult = .failure(APIError.transport)
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "La banca diventa proprietaria del denaro"

        await viewModel.submit()

        XCTAssertEqual(viewModel.phase, .answering(try card()))
        XCTAssertEqual(viewModel.draft, "La banca diventa proprietaria del denaro")
        XCTAssertEqual(drafts.drafts.values.first, "La banca diventa proprietaria del denaro")
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testADraftSurvivesTheScreenBeingRebuilt() async throws {
        let first = makeViewModel()
        await first.start()
        first.beginRecall()
        first.draft = "Half-typed answer"

        repository.cards = ResultQueue([
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardLearn)),
        ])
        let second = makeViewModel()
        await second.start()

        XCTAssertEqual(second.draft, "Half-typed answer")
    }

    func testBlankAnswerIsNeverSent() async {
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "   "

        XCTAssertFalse(viewModel.canSubmit)
        await viewModel.submit()
        XCTAssertTrue(repository.submittedTexts.isEmpty)
    }

    func testOverrideShowsTheUsersGradeAndKeepsTheAIEvaluation() async throws {
        repository.overrideResult = .success(try Fixtures.decode(AnswerResult.self, Fixtures.override))
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "An answer"
        await viewModel.submit()

        await viewModel.override(with: .hard)

        XCTAssertEqual(repository.overrides, [.hard])
        guard case .result(_, let result) = viewModel.phase else {
            return XCTFail("Expected a result")
        }
        XCTAssertEqual(result.finalOutcome, .hard)
        XCTAssertEqual(result.resolvedOutcome, .good)
        XCTAssertEqual(result.evaluation?.classification, .correct)
        // The override replaces the answer's entry instead of counting twice.
        XCTAssertEqual(viewModel.answeredCount, 1)
        XCTAssertEqual(viewModel.count(of: .hard), 1)
    }

    func testFailedEvaluationAsksForASelfGradeOrRetry() async throws {
        let failed = try Fixtures.decode(AnswerResult.self, Fixtures.answerFailed)
        repository.submitResult = .success(failed)
        repository.retryResult = .success(try Fixtures.decode(AnswerResult.self, Fixtures.answerResult))
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "An answer"

        await viewModel.submit()
        guard case .result(_, let pending) = viewModel.phase else { return XCTFail("No result") }
        XCTAssertTrue(pending.needsSelfGrade)
        XCTAssertEqual(viewModel.answeredCount, 0)

        await viewModel.retryEvaluation()
        guard case .result(_, let retried) = viewModel.phase else { return XCTFail("No result") }
        XCTAssertEqual(retried.finalOutcome, .good)
    }

    func testAPendingAnswerComesBackAsItsResult() async throws {
        repository.cards = ResultQueue([
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardPending)),
        ])
        repository.answer = .success(try Fixtures.decode(AnswerResult.self, Fixtures.answerFailed))
        let viewModel = makeViewModel(.practiceHard)

        await viewModel.start()

        guard case .result(_, let result) = viewModel.phase else {
            return XCTFail("Expected the pending answer, got \(viewModel.phase)")
        }
        XCTAssertTrue(result.needsSelfGrade)
    }

    func testNothingToStudyIsAnEmptyStateNotAnError() async {
        repository.startResult = .failure(APIError.server(
            status: 409, errorType: "conflict",
            message: "There is nothing to study in this selection right now."
        ))
        let viewModel = makeViewModel(.scheduledReview)

        await viewModel.start()

        XCTAssertEqual(viewModel.phase, .empty)
    }

    func testStartFailureIsShown() async {
        repository.startResult = .failure(APIError.transport)
        let viewModel = makeViewModel()

        await viewModel.start()

        XCTAssertEqual(viewModel.phase, .failed(APIError.transport.localizedDescription))
    }

    func testSkipMovesToTheNextCard() async throws {
        repository.cards = ResultQueue([
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardLearn)),
            .success(try Fixtures.decode(SessionCard.self, Fixtures.cardDone)),
        ])
        let viewModel = makeViewModel()
        await viewModel.start()

        await viewModel.skip()

        XCTAssertEqual(repository.skips, 1)
        XCTAssertEqual(viewModel.phase, .finished)
    }

    func testSubmitConflictResyncsWithoutLosingTheDraft() async throws {
        repository.submitResult = .failure(APIError.server(
            status: 409, errorType: "conflict", message: "Already answered"
        ))
        let viewModel = makeViewModel()
        await viewModel.start()
        viewModel.beginRecall()
        viewModel.draft = "Typed before the conflict"

        await viewModel.submit()

        XCTAssertEqual(drafts.drafts.values.first, "Typed before the conflict")
    }
}
