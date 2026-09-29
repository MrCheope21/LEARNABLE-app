import Foundation
import Observation
import SwiftUI  // MutableCollection.move(fromOffsets:toOffset:)

/// Reviewing an AI curriculum proposal (docs/PROJECT_SPEC.md §20). The user renames, deletes,
/// reorders and adds items locally, then applies the edited tree in one request, or rejects it.
/// Only what the API supports: one apply with the edited tree, or a delete.
@MainActor
@Observable
final class ProposalReviewViewModel {
    struct DraftConcept: Identifiable, Equatable {
        let id = UUID()
        var title: String
        var description: String
        var existingConceptId: UUID?
        var sources: [SourceReference]
    }

    struct DraftTopic: Identifiable, Equatable {
        let id = UUID()
        var title: String
        var description: String
        var existingTopicId: UUID?
        var concepts: [DraftConcept]
    }

    struct DraftChapter: Identifiable, Equatable {
        let id = UUID()
        var title: String
        var description: String
        var topics: [DraftTopic]
    }

    let route: ProposalRoute
    private(set) var state: Loadable<CurriculumProposal> = .loading
    /// Chapter-scope proposals edit `topics`; Course-scope ones edit `chapters`.
    var topics: [DraftTopic] = []
    var chapters: [DraftChapter] = []
    private(set) var isSubmitting = false
    /// Applied or rejected: the view pops back.
    private(set) var isFinished = false
    var errorMessage: String?

    private let repository: CurriculumRepository
    private let pollInterval: Duration
    private let maxPolls: Int

    init(
        route: ProposalRoute,
        repository: CurriculumRepository,
        pollInterval: Duration = .seconds(1.5),
        maxPolls: Int = 120
    ) {
        self.route = route
        self.repository = repository
        self.pollInterval = pollInterval
        self.maxPolls = maxPolls
    }

    var isChapterScope: Bool { state.value?.chapterId != nil }

    var isEmpty: Bool { isChapterScope ? topics.isEmpty : chapters.isEmpty }

    /// Loads the proposal, following it while the AI is still generating.
    func load() async {
        do {
            var proposal = try await repository.fetchProposal(id: route.proposalId)
            var polls = 0
            while proposal.status == .generating && polls < maxPolls {
                state = .loaded(proposal)
                polls += 1
                try await Task.sleep(for: pollInterval)
                proposal = try await repository.fetchProposal(id: route.proposalId)
            }
            topics = (proposal.topics ?? []).map(Self.draft)
            chapters = (proposal.chapters ?? []).map {
                DraftChapter(title: $0.title, description: $0.description,
                             topics: $0.topics.map(Self.draft))
            }
            state = .loaded(proposal)
        } catch is CancellationError {
            return
        } catch {
            state = .failed(userMessage(for: error))
        }
    }

    // MARK: - Editing (Chapter scope)

    func deleteTopic(_ topic: DraftTopic) {
        topics.removeAll { $0.id == topic.id }
    }

    func deleteConcept(_ concept: DraftConcept, from topic: DraftTopic) {
        guard let index = topics.firstIndex(where: { $0.id == topic.id }) else { return }
        topics[index].concepts.removeAll { $0.id == concept.id }
    }

    func moveConcepts(in topic: DraftTopic, from source: IndexSet, to destination: Int) {
        guard let index = topics.firstIndex(where: { $0.id == topic.id }) else { return }
        topics[index].concepts.move(fromOffsets: source, toOffset: destination)
    }

    /// A Concept the AI missed, typed by the user (it has no source passages).
    func addConcept(to topic: DraftTopic) {
        guard let index = topics.firstIndex(where: { $0.id == topic.id }) else { return }
        topics[index].concepts.append(
            DraftConcept(title: "", description: "", existingConceptId: nil, sources: [])
        )
    }

    // MARK: - Editing (Course scope)

    func deleteChapter(_ chapter: DraftChapter) {
        chapters.removeAll { $0.id == chapter.id }
    }

    func deleteTopic(_ topic: DraftTopic, from chapter: DraftChapter) {
        guard let index = chapters.firstIndex(where: { $0.id == chapter.id }) else { return }
        chapters[index].topics.removeAll { $0.id == topic.id }
    }

    // MARK: - Decisions

    /// Every item needs a title; the backend would refuse the tree otherwise.
    var hasBlankTitles: Bool {
        let topicList = isChapterScope ? topics : chapters.flatMap(\.topics)
        let blankChapter = !isChapterScope && chapters.contains { isBlank($0.title) }
        return blankChapter || topicList.contains { topic in
            isBlank(topic.title) || topic.concepts.contains { isBlank($0.title) }
        }
    }

    func apply() async {
        guard !isEmpty else { return }
        guard !hasBlankTitles else {
            errorMessage = String(localized: "Every chapter, topic and concept needs a title.")
            return
        }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await repository.applyProposal(id: route.proposalId, body: body())
            isFinished = true
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    func reject() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            try await repository.rejectProposal(id: route.proposalId)
            isFinished = true
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    func body() -> CurriculumApplyBody {
        if isChapterScope {
            return CurriculumApplyBody(chapters: nil, topics: topics.map(Self.applyTopic))
        }
        return CurriculumApplyBody(
            chapters: chapters.map {
                ApplyChapter(
                    title: trimmed($0.title),
                    description: $0.description,
                    topics: $0.topics.map(Self.applyTopic)
                )
            },
            topics: nil
        )
    }

    private static func draft(_ topic: ProposedTopic) -> DraftTopic {
        DraftTopic(
            title: topic.title,
            description: topic.description,
            existingTopicId: topic.existingTopicId,
            concepts: topic.concepts.map {
                DraftConcept(
                    title: $0.title,
                    description: $0.description,
                    existingConceptId: $0.existingConceptId,
                    sources: $0.sources
                )
            }
        )
    }

    private static func applyTopic(_ topic: DraftTopic) -> ApplyTopic {
        ApplyTopic(
            title: trimmed(topic.title),
            description: topic.description,
            existingTopicId: topic.existingTopicId,
            concepts: topic.concepts.map {
                ApplyConcept(
                    title: trimmed($0.title),
                    description: $0.description,
                    existingConceptId: $0.existingConceptId,
                    sourceChunkIds: $0.sources.map(\.chunkId)
                )
            }
        )
    }

    private func isBlank(_ text: String) -> Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

private func trimmed(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
}
