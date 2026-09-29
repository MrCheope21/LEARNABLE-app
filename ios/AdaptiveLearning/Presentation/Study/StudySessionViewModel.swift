import Foundation
import Observation

/// One study session: LEARN, SCHEDULED_REVIEW or PRACTICE (docs/API.md "Review sessions").
///
/// The backend picks the questions, evaluates answers, resolves outcomes and moves the schedule;
/// this only drives the screens. It never computes a memory level or a due date.
///
/// An answer is never lost (docs/PROJECT_SPEC.md §79): the draft is saved on every change and
/// cleared only once the backend has stored the answer. A failed submission keeps the text in
/// the editor.
@MainActor
@Observable
final class StudySessionViewModel {
    enum Phase: Equatable {
        case starting
        /// LEARN: what to encode, before the first recall.
        case introduction(StudyCard)
        case answering(StudyCard)
        case submitting(StudyCard)
        case result(StudyCard, AnswerResult)
        case finished
        /// Nothing qualifies for this session right now (e.g. nothing due).
        case empty
        case failed(String)
    }

    let courseId: UUID
    let courseTitle: String
    let request: SessionRequest

    private(set) var phase: Phase = .starting
    private(set) var session: ReviewSession?
    /// The answer being typed. Persisted locally on every change.
    var draft = "" {
        didSet { persistDraft() }
    }
    /// A failure the user can recover from on the same screen (the draft is kept).
    var errorMessage: String?
    /// An override or evaluation retry in flight.
    private(set) var isWorking = false
    /// Final outcomes of this sitting, by answer (an override replaces its answer's entry).
    private(set) var outcomes: [UUID: ReviewOutcome] = [:]

    private let repository: ReviewRepository
    private let drafts: AnswerDraftStore
    private var draftKey: String?

    init(
        courseId: UUID,
        courseTitle: String,
        request: SessionRequest,
        repository: ReviewRepository,
        drafts: AnswerDraftStore
    ) {
        self.courseId = courseId
        self.courseTitle = courseTitle
        self.request = request
        self.repository = repository
        self.drafts = drafts
    }

    var intent: SessionIntent { request.intent }

    var canSubmit: Bool {
        guard case .answering = phase else { return false }
        return !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var answeredCount: Int { outcomes.count }

    func count(of outcome: ReviewOutcome) -> Int {
        outcomes.values.filter { $0 == outcome }.count
    }

    // MARK: - Flow

    func start() async {
        phase = .starting
        do {
            session = try await repository.startSession(courseId: courseId, request: request)
        } catch is CancellationError {
            return
        } catch APIError.server(409, _, _) {
            // The only conflict when starting: nothing qualifies (docs/API.md `empty_pool`).
            phase = .empty
            return
        } catch {
            phase = .failed(userMessage(for: error))
            return
        }
        await loadNext()
    }

    /// Fetches the current card. A card with an answer still waiting for an outcome (e.g. the
    /// app closed after a failed evaluation) comes back as its result, so it can be graded.
    func loadNext() async {
        guard let session else { return }
        do {
            let next = try await repository.nextCard(sessionId: session.id)
            self.session = next.session
            guard !next.done, let card = next.card else {
                phase = .finished
                return
            }
            if let pendingId = card.pendingAnswerId {
                let result = try await repository.fetchAnswer(id: pendingId)
                phase = .result(card, result)
                return
            }
            restoreDraft(for: card)
            phase = card.introduction == nil ? .answering(card) : .introduction(card)
        } catch is CancellationError {
            return
        } catch {
            phase = .failed(userMessage(for: error))
        }
    }

    /// LEARN: done reading the introduction; now recall without it.
    func beginRecall() {
        if case .introduction(let card) = phase {
            phase = .answering(card)
        }
    }

    func submit() async {
        guard canSubmit, case .answering(let card) = phase, let session else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        phase = .submitting(card)
        do {
            let result = try await repository.submitAnswer(
                sessionId: session.id, questionId: card.question.id, text: text
            )
            // The backend has the answer now: the local copy can go.
            clearDraft()
            draft = ""
            record(result)
            phase = .result(card, result)
        } catch is CancellationError {
            phase = .answering(card)
        } catch APIError.server(409, _, _) {
            // The session moved on without us, e.g. the answer reached the server but the
            // response was lost. Resync; the draft stays saved.
            await loadNext()
        } catch {
            phase = .answering(card)
            errorMessage = userMessage(for: error)
        }
    }

    /// After a failed (or unconfigured) evaluation.
    func retryEvaluation() async {
        guard case .result(let card, let result) = phase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let updated = try await repository.retryEvaluation(answerId: result.answerId)
            record(updated)
            phase = .result(card, updated)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    /// The user's own grade. The backend keeps the AI evaluation as it was.
    func override(with outcome: ReviewOutcome) async {
        guard case .result(let card, let result) = phase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let updated = try await repository.override(answerId: result.answerId, outcome: outcome)
            record(updated)
            phase = .result(card, updated)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    /// Moves past the current card without an outcome; its memory state is untouched.
    func skip() async {
        guard let session else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            _ = try await repository.skip(sessionId: session.id)
            await loadNext()
        } catch is CancellationError {
            return
        } catch {
            errorMessage = userMessage(for: error)
        }
    }

    func end() async {
        guard let session, session.endedAt == nil else { return }
        try? await repository.endSession(sessionId: session.id)
    }

    // MARK: - Private

    private func record(_ result: AnswerResult) {
        if let outcome = result.finalOutcome {
            outcomes[result.answerId] = outcome
        }
    }

    private func restoreDraft(for card: StudyCard) {
        // Keyed by question, which is stable across sessions: a draft survives the app being
        // closed and the same question coming back later.
        let key = "question.\(card.question.id.uuidString)"
        draftKey = nil
        draft = drafts.load(key: key) ?? ""
        draftKey = key
    }

    private func persistDraft() {
        guard let draftKey else { return }
        if draft.isEmpty {
            drafts.clear(key: draftKey)
        } else {
            drafts.save(draft, key: draftKey)
        }
    }

    private func clearDraft() {
        if let draftKey {
            drafts.clear(key: draftKey)
        }
        draftKey = nil
    }
}
