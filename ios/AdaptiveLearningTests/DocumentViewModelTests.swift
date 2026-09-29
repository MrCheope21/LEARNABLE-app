import XCTest
@testable import AdaptiveLearning

@MainActor
final class CourseDetailViewModelTests: XCTestCase {
    private func makeViewModel(
        _ repository: FakeDocumentRepository,
        maxUploadBytes: Int = CourseDetailViewModel.defaultMaxUploadBytes
    ) -> CourseDetailViewModel {
        CourseDetailViewModel(
            course: .sample(),
            repository: repository,
            pollInterval: .milliseconds(1),
            maxUploadBytes: maxUploadBytes
        )
    }

    func testLoadShowsTheCoursesDocuments() async {
        let repository = FakeDocumentRepository()
        repository.documentResponses = [.success([.sample(filename: "bilancio.pdf")])]
        let viewModel = makeViewModel(repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.documents.map(\.filename), ["bilancio.pdf"])
        XCTAssertTrue(viewModel.hasLoaded)
    }

    func testStatusesRefreshUntilProcessingFinishes() async {
        let id = UUID()
        let repository = FakeDocumentRepository()
        repository.documentResponses = [
            .success([.sample(id: id, status: .processing)]),
            .success([.sample(id: id, status: .processing)]),
            .success([.sample(id: id, status: .ready)]),
        ]
        let viewModel = makeViewModel(repository)
        await viewModel.load()

        await viewModel.refreshUntilProcessed()

        XCTAssertEqual(viewModel.documents.map(\.status), [.ready])
        XCTAssertEqual(repository.fetchCount, 3)
    }

    func testPollingStopsAndReportsOnFailure() async {
        let repository = FakeDocumentRepository()
        repository.documentResponses = [
            .success([.sample(status: .processing)]),
            .failure(APIError.transport),
        ]
        let viewModel = makeViewModel(repository)
        await viewModel.load()

        await viewModel.refreshUntilProcessed()

        XCTAssertEqual(repository.fetchCount, 2)
        XCTAssertEqual(viewModel.errorMessage, APIError.transport.localizedDescription)
    }

    func testUploadAddsTheDocumentAndFollowsItToReady() async {
        let uploaded = CourseDocument.sample(filename: "appunti.pdf", status: .processing)
        var ready = uploaded
        ready.status = .ready
        let repository = FakeDocumentRepository()
        repository.uploadResult = .success(uploaded)
        repository.documentResponses = [.success([ready])]
        let viewModel = makeViewModel(repository)

        await viewModel.upload(fileName: "appunti.pdf", data: Data("pdf".utf8))

        XCTAssertEqual(repository.uploads.map { $0.fileName }, ["appunti.pdf"])
        XCTAssertEqual(viewModel.documents.map(\.status), [.ready])
        XCTAssertFalse(viewModel.isUploading)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testDuplicateUploadShowsAFriendlyMessage() async {
        let repository = FakeDocumentRepository()
        repository.uploadResult = .failure(APIError.server(
            status: 409, errorType: "conflict", message: "This file is already in the course."
        ))
        let viewModel = makeViewModel(repository)

        await viewModel.upload(fileName: "a.pdf", data: Data("pdf".utf8))

        XCTAssertEqual(
            viewModel.errorMessage, String(localized: "This file is already in the course.")
        )
        XCTAssertTrue(viewModel.documents.isEmpty)
        XCTAssertFalse(viewModel.isUploading)
    }

    func testOversizedFileIsRefusedWithoutUploading() async {
        let repository = FakeDocumentRepository()
        let viewModel = makeViewModel(repository, maxUploadBytes: 10)

        await viewModel.upload(fileName: "big.pdf", data: Data(count: 11))

        XCTAssertTrue(repository.uploads.isEmpty)
        XCTAssertEqual(
            viewModel.errorMessage, String(localized: "This file is too large (max 50 MB).")
        )
    }

    func testDeleteRemovesTheDocument() async {
        let document = CourseDocument.sample()
        let repository = FakeDocumentRepository()
        repository.documentResponses = [.success([document])]
        let viewModel = makeViewModel(repository)
        await viewModel.load()

        await viewModel.delete(document)

        XCTAssertEqual(repository.deletedIds, [document.id])
        XCTAssertTrue(viewModel.documents.isEmpty)
    }

    func testFailedDeleteKeepsTheDocumentAndExplains() async {
        let document = CourseDocument.sample()
        let repository = FakeDocumentRepository()
        repository.documentResponses = [.success([document])]
        repository.deleteError = APIError.transport
        let viewModel = makeViewModel(repository)
        await viewModel.load()

        await viewModel.delete(document)

        XCTAssertEqual(viewModel.documents, [document])
        XCTAssertNotNil(viewModel.errorMessage)
    }
}

@MainActor
final class SourcePassagesViewModelTests: XCTestCase {
    func testLoadsPageByPageUntilExhausted() async {
        let pageSize = SourcePassagesViewModel.pageSize
        let repository = FakeDocumentRepository()
        repository.passages = SourcePassage.samples(count: pageSize + 7)
        let viewModel = SourcePassagesViewModel(document: .sample(), repository: repository)

        await viewModel.loadMore()
        XCTAssertEqual(viewModel.passages.count, pageSize)
        XCTAssertTrue(viewModel.hasMore)

        await viewModel.loadMore()
        XCTAssertEqual(viewModel.passages.count, pageSize + 7)
        XCTAssertFalse(viewModel.hasMore)

        await viewModel.loadMore()  // nothing left: no further request
        XCTAssertEqual(repository.passageRequests.map { $0.offset }, [0, pageSize])
        XCTAssertEqual(viewModel.passages.map(\.position), Array(0..<(pageSize + 7)))
    }
}

final class CourseDocumentDecodingTests: XCTestCase {
    func testDecodesTheBackendShape() throws {
        let json = Data("""
        [{"id": "3f2b8c4e-1d2a-4b5c-9e8f-7a6b5c4d3e2f",
          "course_id": "8a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
          "filename": "bilancio.pdf", "mime_type": "application/pdf", "kind": "PDF",
          "size_bytes": 25600, "sha256": "ab", "status": "READY", "error_message": null,
          "page_count": 40, "chunk_count": 40, "source_created_at": null,
          "created_at": "2026-09-23T08:42:33.720Z", "updated_at": "2026-09-23T08:42:34.000Z"}]
        """.utf8)

        let documents = try JSONDecoder.apiDecoder.decode([CourseDocument].self, from: json)

        XCTAssertEqual(documents.first?.status, .ready)
        XCTAssertEqual(documents.first?.pageCount, 40)
        XCTAssertEqual(documents.first?.kind, .pdf)
    }

    func testAnUnknownKindDoesNotBreakTheList() throws {
        let json = Data("""
        [{"id": "3f2b8c4e-1d2a-4b5c-9e8f-7a6b5c4d3e2f",
          "course_id": "8a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
          "filename": "audio.m4a", "kind": "AUDIO", "size_bytes": 1, "status": "FAILED",
          "error_message": "Not supported", "page_count": null, "chunk_count": 0,
          "created_at": "2026-09-23T08:42:33.720Z"}]
        """.utf8)

        let documents = try JSONDecoder.apiDecoder.decode([CourseDocument].self, from: json)

        XCTAssertEqual(documents.first?.kind, .unknown)
    }
}
