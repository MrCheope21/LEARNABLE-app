import Foundation
import Observation

/// "View source" for one document: its passages in order, with page and section
/// (docs/PROJECT_SPEC.md §18, §66). Loaded a page at a time; long textbooks have thousands.
@MainActor
@Observable
final class SourcePassagesViewModel {
    static let pageSize = 50

    let document: CourseDocument
    private(set) var passages: [SourcePassage] = []
    private(set) var hasMore = true
    private(set) var isLoading = false
    var errorMessage: String?

    private let repository: DocumentRepository

    init(document: CourseDocument, repository: DocumentRepository) {
        self.document = document
        self.repository = repository
    }

    func loadMore() async {
        guard hasMore, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let page = try await repository.fetchPassages(
                documentId: document.id, offset: passages.count, limit: Self.pageSize
            )
            passages.append(contentsOf: page)
            hasMore = page.count == Self.pageSize
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
