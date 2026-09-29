import Foundation
import Observation

/// "View source" for one referenced passage (docs/PROJECT_SPEC.md §18, §66): a trust feature,
/// reachable from feedback and from Learning Items.
@MainActor
@Observable
final class SourceViewModel {
    let reference: SourceReference
    private(set) var state: Loadable<SourcePassage> = .loading

    private let repository: DocumentRepository

    init(reference: SourceReference, repository: DocumentRepository) {
        self.reference = reference
        self.repository = repository
    }

    func load() async {
        state = .loading
        do {
            state = .loaded(
                try await repository.fetchPassage(
                    documentId: reference.documentId, passageId: reference.chunkId
                )
            )
        } catch is CancellationError {
            return
        } catch {
            state = .failed(userMessage(for: error))
        }
    }
}
