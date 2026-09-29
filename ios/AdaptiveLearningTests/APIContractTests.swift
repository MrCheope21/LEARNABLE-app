import XCTest
@testable import AdaptiveLearning

/// Every model the vertical slice uses, decoded from a real backend response (Fixtures.swift).
/// A renamed or retyped field on either side fails here instead of on a device.
final class APIContractTests: XCTestCase {
    func testCurriculumResponsesDecode() throws {
        let outline = try Fixtures.decode([ChapterNode].self, Fixtures.outline)
        XCTAssertFalse(outline.isEmpty)
        XCTAssertFalse(outline[0].topics.isEmpty)

        let concept = try Fixtures.decode(Concept.self, Fixtures.concept)
        XCTAssertEqual(concept.studyState, .active)
        XCTAssertEqual(concept.itemGenerationStatus, .ready)

        let activated = try Fixtures.decode(Concept.self, Fixtures.conceptActivated)
        XCTAssertEqual(activated.itemGenerationStatus, .generating)
    }

    func testProposalResponsesDecode() throws {
        let generating = try Fixtures.decode(CurriculumProposal.self, Fixtures.proposalGenerating)
        XCTAssertEqual(generating.status, .generating)

        let ready = try Fixtures.decode(CurriculumProposal.self, Fixtures.proposalReady)
        XCTAssertEqual(ready.status, .ready)
        XCTAssertNotNil(ready.chapterId)
        let source = try XCTUnwrap(ready.topics?.first?.concepts.first?.sources.first)
        XCTAssertEqual(source.documentName, "banca.md")
    }

    func testLearningItemsAndSourcesDecode() throws {
        let items = try Fixtures.decode([LearningItem].self, Fixtures.learningItems)
        XCTAssertFalse(items.isEmpty)
        XCTAssertFalse(items[0].questions.isEmpty)

        let sources = try Fixtures.decode([SourcePassage].self, Fixtures.itemSources)
        XCTAssertEqual(sources.first?.section, "Il deposito bancario")
        _ = try Fixtures.decode(SourcePassage.self, Fixtures.chunk)
    }

    func testSessionResponsesDecode() throws {
        let session = try Fixtures.decode(ReviewSession.self, Fixtures.session)
        XCTAssertEqual(session.intent, .learn)

        let learn = try Fixtures.decode(SessionCard.self, Fixtures.cardLearn)
        XCTAssertNotNil(learn.card?.introduction)
        XCTAssertNil(learn.card?.pendingAnswerId)

        let done = try Fixtures.decode(SessionCard.self, Fixtures.cardDone)
        XCTAssertTrue(done.done)
        XCTAssertNil(done.card)

        let pending = try Fixtures.decode(SessionCard.self, Fixtures.cardPending)
        XCTAssertNotNil(pending.card?.pendingAnswerId)
    }

    func testAnswerResponsesDecode() throws {
        let result = try Fixtures.decode(AnswerResult.self, Fixtures.answerResult)
        XCTAssertEqual(result.finalOutcome, .good)
        XCTAssertEqual(result.evaluation?.status, .completed)
        XCTAssertNotNil(result.schedule?.nextDueAt)
        XCTAssertEqual(result.reference.sources.first?.documentName, "banca.md")

        let overridden = try Fixtures.decode(AnswerResult.self, Fixtures.override)
        XCTAssertEqual(overridden.resolvedOutcome, .good)
        XCTAssertEqual(overridden.overrideOutcome, .hard)
        XCTAssertEqual(overridden.finalOutcome, .hard)

        let failed = try Fixtures.decode(AnswerResult.self, Fixtures.answerFailed)
        XCTAssertEqual(failed.evaluation?.status, .failed)
        XCTAssertTrue(failed.needsSelfGrade)
        XCTAssertNil(failed.finalOutcome)

        _ = try Fixtures.decode(AnswerResult.self, Fixtures.answerDetail)
    }

    func testProgressResponsesDecode() throws {
        let progress = try Fixtures.decode(CourseProgress.self, Fixtures.progress)
        XCTAssertEqual(progress.curriculum.active, 1)
        XCTAssertEqual(progress.memory.markedHard, 1)
        XCTAssertEqual(progress.reviewLoad.laterToday, 1)

        let load = try Fixtures.decode(ReviewLoad.self, Fixtures.reviewLoad)
        XCTAssertEqual(load.today, 1)

        let home = try Fixtures.decode(HomeSummary.self, Fixtures.home)
        XCTAssertEqual(home.courses.first?.weakConcepts.first?.markedHard, 1)
    }

    func testDocumentResponsesDecode() throws {
        _ = try Fixtures.decode([Course].self, Fixtures.courses)
        _ = try Fixtures.decode(CourseDocument.self, Fixtures.upload)
        _ = try Fixtures.decode([CourseDocument].self, Fixtures.documents)
    }

    func testUnknownEnumValuesDoNotBreakDecoding() throws {
        let json = Fixtures.concept.replacingOccurrences(of: "\"ACTIVE\"", with: "\"ARCHIVED\"")
        let concept = try Fixtures.decode(Concept.self, json)
        XCTAssertEqual(concept.studyState, .unknown)
    }

    func testSessionRequestEncodesTheBackendsFieldNames() throws {
        let data = try JSONEncoder.apiEncoder.encode(SessionRequest.practiceHard)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["intent"] as? String, "PRACTICE")
        XCTAssertEqual(object["selection_mode"] as? String, "MARKED_HARD")
        XCTAssertEqual(object["update_schedule"] as? Bool, false)
    }
}
