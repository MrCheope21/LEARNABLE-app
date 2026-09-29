import Foundation
import Observation
import UniformTypeIdentifiers

/// Study material: a Course's whole Knowledge Repository, or one Chapter's (docs/PROJECT_SPEC.md
/// §16). Imports go into the Chapter when one is set.
@MainActor
@Observable
final class CourseDetailViewModel {
    /// What the Files picker offers; the backend decides the real type from the content anyway.
    static let importableTypes: [UTType] = [UTType.pdf, UTType.plainText, UTType.image] + [
        "org.openxmlformats.wordprocessingml.document",
        "org.openxmlformats.presentationml.presentation",
        "net.daringfireball.markdown",
    ].compactMap { UTType($0) }

    /// Mirrors the backend's default MAX_UPLOAD_MB, so an oversized file is refused before it's
    /// read or sent rather than after a long upload.
    static let defaultMaxUploadBytes = 50 * 1024 * 1024

    let course: Course
    /// Set: this screen shows and imports one Chapter's material.
    let chapterId: UUID?
    private(set) var documents: [CourseDocument] = []
    private(set) var hasLoaded = false
    private(set) var isUploading = false
    var isImporting = false
    var errorMessage: String?

    private let repository: DocumentRepository
    private let pollInterval: Duration
    private let maxUploadBytes: Int
    private var isPolling = false

    init(
        course: Course,
        chapterId: UUID? = nil,
        repository: DocumentRepository,
        pollInterval: Duration = .seconds(1.5),
        maxUploadBytes: Int = CourseDetailViewModel.defaultMaxUploadBytes
    ) {
        self.course = course
        self.chapterId = chapterId
        self.repository = repository
        self.pollInterval = pollInterval
        self.maxUploadBytes = maxUploadBytes
    }

    func load() async {
        do {
            documents = try await repository.fetchDocuments(courseId: course.id, chapterId: chapterId)
            hasLoaded = true
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Re-fetches while any document is still PROCESSING, so statuses update on their own.
    /// Stops when all are done, on the first failure, or when the view goes away (cancellation).
    func refreshUntilProcessed() async {
        guard !isPolling else { return }
        isPolling = true
        defer { isPolling = false }
        while documents.contains(where: { $0.status == .processing }) {
            do {
                try await Task.sleep(for: pollInterval)
                documents = try await repository.fetchDocuments(courseId: course.id, chapterId: chapterId)
            } catch is CancellationError {
                return
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }
    }

    /// A file picked in the Files app. Access to it is granted only inside the security scope.
    func importFile(at url: URL) async {
        let accessing = url.startAccessingSecurityScopedResource()
        defer {
            if accessing { url.stopAccessingSecurityScopedResource() }
        }
        if let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize,
           size > maxUploadBytes {
            errorMessage = String(localized: "This file is too large (max 50 MB).")
            return
        }
        let data: Data
        do {
            // Off the main actor: study PDFs can be tens of megabytes.
            data = try await Task.detached { try Data(contentsOf: url) }.value
        } catch {
            errorMessage = String(localized: "The file couldn't be read.")
            return
        }
        await upload(fileName: url.lastPathComponent, data: data)
    }

    func upload(fileName: String, data: Data) async {
        guard data.count <= maxUploadBytes else {
            errorMessage = String(localized: "This file is too large (max 50 MB).")
            return
        }
        isUploading = true
        do {
            let document = try await repository.uploadDocument(
                courseId: course.id, chapterId: chapterId, fileName: fileName, data: data
            )
            documents.append(document)
        } catch is CancellationError {
            isUploading = false
            return
        } catch APIError.server(_, "conflict", _) {
            isUploading = false
            errorMessage = String(localized: "This file is already in the course.")
            return
        } catch {
            isUploading = false
            errorMessage = error.localizedDescription
            return
        }
        // Polling is not "uploading": the spinner goes away once the file is safely stored.
        isUploading = false
        await refreshUntilProcessed()
    }

    func delete(_ document: CourseDocument) async {
        do {
            try await repository.deleteDocument(id: document.id)
            documents.removeAll { $0.id == document.id }
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func passagesViewModel(for document: CourseDocument) -> SourcePassagesViewModel {
        SourcePassagesViewModel(document: document, repository: repository)
    }
}
