import XCTest
@testable import AdaptiveLearning

@MainActor
final class ConceptViewModelTests: XCTestCase {
    private let route = ConceptRoute(course: .sample(), conceptId: UUID(), title: "Deposito")

    func testActivationFollowsGenerationUntilItemsAreReady() async throws {
        let items = try Fixtures.decode([LearningItem].self, Fixtures.learningItems)
        let repository = FakeConceptRepository(concept: [
            .success(.sample(state: .notStudied)),
            .success(.sample(state: .active, generation: .generating)),
            .success(.sample(state: .active, generation: .generating)),
            .success(.sample(state: .active, generation: .ready)),
        ])
        repository.items = .success([])
        let viewModel = ConceptViewModel(
            route: route, concepts: repository, progress: FakeProgressRepository(),
            pollInterval: .milliseconds(1)
        )
        await viewModel.load()
        repository.items = .success(items)

        await viewModel.perform(.activate)

        XCTAssertEqual(repository.actions, [.activate])
        XCTAssertEqual(viewModel.concept?.itemGenerationStatus, .ready)
        XCTAssertFalse(viewModel.isGenerating)
        XCTAssertEqual(viewModel.state.value?.items.count, items.count)
    }

    func testPollingGivesUpAfterTheLimit() async {
        let repository = FakeConceptRepository(concept: [
            .success(.sample(state: .active, generation: .generating)),
        ])
        let viewModel = ConceptViewModel(
            route: route, concepts: repository, progress: FakeProgressRepository(),
            pollInterval: .milliseconds(1), maxPolls: 3
        )

        await viewModel.load()

        XCTAssertEqual(repository.conceptFetches, 4)  // load + 3 polls
        XCTAssertTrue(viewModel.isGenerating)
    }

    func testItemsToLearnCountsOnlyNewTrainedItemsOfAnActiveConcept() async throws {
        var items = try Fixtures.decode([LearningItem].self, Fixtures.learningItems)
        items = items.map { item in
            var item = item
            item.reviewState.state = .new
            return item
        }
        let repository = FakeConceptRepository(concept: [.success(.sample(state: .active, generation: .ready))])
        repository.items = .success(items)
        let viewModel = ConceptViewModel(route: route, concepts: repository, progress: FakeProgressRepository())

        await viewModel.load()

        let expected = items.filter { $0.inTraining && !$0.paused }.count
        XCTAssertEqual(viewModel.itemsToLearn, expected)
    }

    func testGenerationWithoutMaterialExplainsWhy() async {
        let repository = FakeConceptRepository(concept: [.success(.sample(state: .active, generation: .failed))])
        repository.generateResult = .failure(APIError.server(status: 409, errorType: "conflict", message: "x"))
        let viewModel = ConceptViewModel(route: route, concepts: repository, progress: FakeProgressRepository())
        await viewModel.load()

        await viewModel.generateItems()

        XCTAssertEqual(
            viewModel.errorMessage,
            String(localized: "This concept has no source material to build learning items from.")
        )
    }

    func testLoadFailureIsRetryable() async {
        let repository = FakeConceptRepository(concept: [.failure(APIError.transport)])
        let viewModel = ConceptViewModel(route: route, concepts: repository, progress: FakeProgressRepository())

        await viewModel.load()

        guard case .failed = viewModel.state else { return XCTFail("Expected failure") }
    }
}

@MainActor
final class ProposalReviewViewModelTests: XCTestCase {
    private func makeViewModel(_ repository: FakeCurriculumRepository) -> ProposalReviewViewModel {
        ProposalReviewViewModel(
            route: ProposalRoute(course: .sample(), proposalId: UUID()),
            repository: repository,
            pollInterval: .milliseconds(1)
        )
    }

    private func readyRepository() throws -> FakeCurriculumRepository {
        let repository = FakeCurriculumRepository()
        repository.proposal = ResultQueue([
            .success(try Fixtures.decode(CurriculumProposal.self, Fixtures.proposalGenerating)),
            .success(try Fixtures.decode(CurriculumProposal.self, Fixtures.proposalReady)),
        ])
        return repository
    }

    func testWaitsForTheAIThenShowsAnEditableDraft() async throws {
        let viewModel = makeViewModel(try readyRepository())

        await viewModel.load()

        XCTAssertEqual(viewModel.state.value?.status, .ready)
        XCTAssertTrue(viewModel.isChapterScope)
        XCTAssertEqual(viewModel.topics.map(\.title), ["Il deposito bancario"])
    }

    func testAppliesTheEditedTreeWithItsSources() async throws {
        let repository = try readyRepository()
        let viewModel = makeViewModel(repository)
        await viewModel.load()
        viewModel.topics[0].title = "  Deposito  "
        viewModel.addConcept(to: viewModel.topics[0])
        viewModel.topics[0].concepts[1].title = "Restituzione"

        await viewModel.apply()

        let body = try XCTUnwrap(repository.appliedBodies.first)
        XCTAssertNil(body.chapters)
        let topic = try XCTUnwrap(body.topics?.first)
        XCTAssertEqual(topic.title, "Deposito")
        XCTAssertEqual(topic.concepts.map(\.title).last, "Restituzione")
        XCTAssertFalse(topic.concepts[0].sourceChunkIds.isEmpty)
        XCTAssertTrue(topic.concepts[1].sourceChunkIds.isEmpty)
        XCTAssertTrue(viewModel.isFinished)
    }

    func testBlankTitlesAreRefusedLocally() async throws {
        let repository = try readyRepository()
        let viewModel = makeViewModel(repository)
        await viewModel.load()
        viewModel.addConcept(to: viewModel.topics[0])

        await viewModel.apply()

        XCTAssertTrue(repository.appliedBodies.isEmpty)
        XCTAssertNotNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.isFinished)
    }

    func testDeletingEverythingDisablesApply() async throws {
        let repository = try readyRepository()
        let viewModel = makeViewModel(repository)
        await viewModel.load()
        viewModel.deleteTopic(viewModel.topics[0])

        XCTAssertTrue(viewModel.isEmpty)
        await viewModel.apply()
        XCTAssertTrue(repository.appliedBodies.isEmpty)
    }

    func testRejectFinishes() async throws {
        let repository = try readyRepository()
        let viewModel = makeViewModel(repository)
        await viewModel.load()

        await viewModel.reject()

        XCTAssertEqual(repository.rejectedIds.count, 1)
        XCTAssertTrue(viewModel.isFinished)
    }
}

@MainActor
final class ChapterViewModelTests: XCTestCase {
    func testAnalyzeOpensTheNewProposal() async throws {
        let outline = try Fixtures.decode([ChapterNode].self, Fixtures.outline)
        let chapter = try XCTUnwrap(outline.first)
        let curriculum = FakeCurriculumRepository()
        let proposal = try Fixtures.decode(CurriculumProposal.self, Fixtures.proposalGenerating)
        curriculum.generateResult = .success(proposal)
        let viewModel = ChapterViewModel(
            route: ChapterRoute(course: .sample(), chapterId: chapter.id, title: chapter.title),
            courses: FakeCourseRepository(), progress: FakeProgressRepository(),
            curriculum: curriculum
        )

        await viewModel.analyzeNewMaterial()

        XCTAssertEqual(curriculum.generatedFor, [chapter.id])
        XCTAssertEqual(viewModel.openProposal?.proposalId, proposal.id)
    }

    func testNothingNewToAnalyzeIsExplained() async {
        let curriculum = FakeCurriculumRepository()
        curriculum.generateResult = .failure(APIError.server(status: 409, errorType: "conflict", message: "x"))
        let viewModel = ChapterViewModel(
            route: ChapterRoute(course: .sample(), chapterId: UUID(), title: "C"),
            courses: FakeCourseRepository(), progress: FakeProgressRepository(),
            curriculum: curriculum
        )

        await viewModel.analyzeNewMaterial()

        XCTAssertNil(viewModel.openProposal)
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testLoadsTheChapterWithItsProgress() async throws {
        let outline = try Fixtures.decode([ChapterNode].self, Fixtures.outline)
        let courses = FakeCourseRepository()
        courses.outline = .success(outline)
        let progress = FakeProgressRepository()
        progress.progress = .success(try Fixtures.decode(CourseProgress.self, Fixtures.progress))
        let viewModel = ChapterViewModel(
            route: ChapterRoute(course: .sample(), chapterId: outline[0].id, title: outline[0].title),
            courses: courses, progress: progress, curriculum: FakeCurriculumRepository()
        )

        await viewModel.load()

        XCTAssertEqual(viewModel.state.value?.chapter.id, outline[0].id)
        XCTAssertNotNil(viewModel.state.value?.progress)
    }
}

@MainActor
final class CourseDashboardViewModelTests: XCTestCase {
    func testAddingAChapterTrimsAndReloads() async throws {
        let courses = FakeCourseRepository()
        let progress = FakeProgressRepository()
        progress.progress = .success(try Fixtures.decode(CourseProgress.self, Fixtures.progress))
        let viewModel = CourseDashboardViewModel(course: .sample(), courses: courses, progress: progress)
        viewModel.newChapterTitle = "  Garanzie  "

        let added = await viewModel.addChapter()

        XCTAssertTrue(added)
        XCTAssertEqual(courses.createdChapters, ["Garanzie"])
        XCTAssertEqual(viewModel.newChapterTitle, "")
        XCTAssertNotNil(viewModel.state.value)
    }

    func testBlankChapterTitleIsNotSent() async {
        let courses = FakeCourseRepository()
        let viewModel = CourseDashboardViewModel(
            course: .sample(), courses: courses, progress: FakeProgressRepository()
        )
        viewModel.newChapterTitle = "   "

        let added = await viewModel.addChapter()

        XCTAssertFalse(added)
        XCTAssertTrue(courses.createdChapters.isEmpty)
    }
}

@MainActor
final class SourceViewModelTests: XCTestCase {
    func testLoadsTheReferencedPassage() async throws {
        let passage = try Fixtures.decode(SourcePassage.self, Fixtures.chunk)
        let repository = FakeDocumentRepository()
        repository.passageResult = .success(passage)
        let reference = SourceReference(
            chunkId: passage.id, documentId: passage.documentId, documentName: "banca.md",
            pageNumber: nil, section: passage.section
        )
        let viewModel = SourceViewModel(reference: reference, repository: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.state.value?.text, passage.text)
    }

    func testMissingPassageShowsAnError() async {
        let repository = FakeDocumentRepository()
        repository.passageResult = .failure(APIError.server(status: 404, errorType: "not_found", message: "x"))
        let reference = SourceReference(
            chunkId: UUID(), documentId: UUID(), documentName: "banca.md", pageNumber: nil, section: nil
        )
        let viewModel = SourceViewModel(reference: reference, repository: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.state, .failed(String(localized: "This item no longer exists.")))
    }
}
