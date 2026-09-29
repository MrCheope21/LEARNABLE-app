import Foundation
import Observation

/// One Concept: study state, activation, its Learning Items and mastery (docs/PROJECT_SPEC.md
/// §21-25). Activating starts Learning Item generation on the backend; this follows it until the
/// items are there. The user decides what to activate: nothing is activated automatically.
@MainActor
@Observable
final class ConceptViewModel {
    struct Content {
        var concept: Concept
        var items: [LearningItem]
        var progress: ConceptProgress?
    }

    let route: ConceptRoute
    private(set) var state: Loadable<Content> = .loading
    /// An action (activate, pause, …) in flight.
    private(set) var isWorking = false
    var errorMessage: String?

    private let concepts: ConceptRepository
    private let progress: ProgressRepository
    private let pollInterval: Duration
    private let maxPolls: Int

    init(
        route: ConceptRoute,
        concepts: ConceptRepository,
        progress: ProgressRepository,
        pollInterval: Duration = .seconds(1.5),
        maxPolls: Int = 80
    ) {
        self.route = route
        self.concepts = concepts
        self.progress = progress
        self.pollInterval = pollInterval
        self.maxPolls = maxPolls
    }

    var concept: Concept? { state.value?.concept }

    var isGenerating: Bool { concept?.itemGenerationStatus == .generating }

    /// New trained items waiting for their first LEARN session.
    var itemsToLearn: Int {
        guard let content = state.value, content.concept.studyState == .active else { return 0 }
        return content.items.filter {
            $0.inTraining && !$0.paused && $0.reviewState.state == .new
        }.count
    }

    func load() async {
        do {
            let concept = try await concepts.fetchConcept(id: route.conceptId)
            let items = try await concepts.fetchLearningItems(conceptId: route.conceptId)
            // Progress is secondary: the screen works without it.
            let conceptProgress = try? await progress.fetchProgress(courseId: route.course.id)
                .concept(route.conceptId)
            state = .loaded(Content(concept: concept, items: items, progress: conceptProgress))
        } catch is CancellationError {
            return
        } catch {
            if state.value == nil {
                state = .failed(userMessage(for: error))
            } else {
                errorMessage = userMessage(for: error)
            }
            return
        }
        await followGeneration()
    }

    func perform(_ action: ConceptAction) async {
        isWorking = true
        defer { isWorking = false }
        do {
            let updated = try await concepts.perform(action, conceptId: route.conceptId)
            replaceConcept(updated)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
            return
        }
        await followGeneration()
        await refreshItemsAndProgress()
    }

    /// Retries generation after it failed or found too little material.
    func generateItems() async {
        isWorking = true
        defer { isWorking = false }
        do {
            replaceConcept(try await concepts.generateLearningItems(conceptId: route.conceptId))
        } catch is CancellationError {
            return
        } catch APIError.server(409, _, _) {
            errorMessage = String(
                localized: "This concept has no source material to build learning items from."
            )
            return
        } catch {
            errorMessage = userMessage(for: error)
            return
        }
        await followGeneration()
    }

    func setInTraining(_ inTraining: Bool, item: LearningItem) async {
        do {
            let updated = try await concepts.setInTraining(inTraining, itemId: item.id)
            guard var content = state.value else { return }
            if let index = content.items.firstIndex(where: { $0.id == item.id }) {
                content.items[index] = updated
                state = .loaded(content)
            }
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    /// Polls while the backend is generating Learning Items, then loads them. Stops when the
    /// view goes away (cancellation) or after `maxPolls`.
    private func followGeneration() async {
        var polls = 0
        while isGenerating && polls < maxPolls {
            polls += 1
            do {
                try await Task.sleep(for: pollInterval)
                replaceConcept(try await concepts.fetchConcept(id: route.conceptId))
            } catch is CancellationError {
                return
            } catch {
                errorMessage = userMessage(for: error)
                return
            }
        }
        if polls > 0 {
            await refreshItemsAndProgress()
        }
    }

    private func refreshItemsAndProgress() async {
        guard var content = state.value else { return }
        do {
            content.items = try await concepts.fetchLearningItems(conceptId: route.conceptId)
            if let courseProgress = try? await progress.fetchProgress(courseId: route.course.id) {
                content.progress = courseProgress.concept(route.conceptId)
            }
            state = .loaded(content)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    private func replaceConcept(_ concept: Concept) {
        guard var content = state.value else { return }
        content.concept = concept
        state = .loaded(content)
    }
}
