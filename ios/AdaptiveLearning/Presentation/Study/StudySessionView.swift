import SwiftUI

/// A focused study session (docs/PROJECT_SPEC.md §65): one question at a time, then the
/// backend's evaluation. Not a chat: the AI is the evaluator inside a structured flow.
struct StudySessionView: View {
    @State private var viewModel: StudySessionViewModel
    let factory: ScreenFactory
    @State private var openSource: SourceReference?
    @Environment(\.dismiss) private var dismiss

    init(viewModel: StudySessionViewModel, factory: ScreenFactory) {
        _viewModel = State(initialValue: viewModel)
        self.factory = factory
    }

    var body: some View {
        NavigationStack {
            content
                .navigationTitle(Text(verbatim: title))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") {
                            Task { await viewModel.end() }
                            dismiss()
                        }
                    }
                    if let session = viewModel.session, session.total > 0 {
                        ToolbarItem(placement: .principal) {
                            Text("\(min(session.position + 1, session.total)) of \(session.total)")
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .errorAlert($viewModel.errorMessage)
                .sheet(item: $openSource) { reference in
                    SourceView(viewModel: factory.source(reference))
                }
                .task { await viewModel.start() }
        }
        .interactiveDismissDisabled()
    }

    private var title: String {
        switch viewModel.intent {
        case .learn: String(localized: "Learn")
        case .scheduledReview: String(localized: "Review")
        case .practice: String(localized: "Practice")
        default: viewModel.courseTitle
        }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.phase {
        case .starting:
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .introduction(let card):
            IntroductionView(card: card, openSource: showSource) {
                viewModel.beginRecall()
            }
        case .answering(let card), .submitting(let card):
            AnswerView(card: card, viewModel: viewModel)
        case .result(let card, let result):
            ResultView(card: card, result: result, viewModel: viewModel, openSource: showSource)
        case .finished:
            FinishedView(viewModel: viewModel) { dismiss() }
        case .empty:
            ContentUnavailableView {
                Label("Nothing to Study", systemImage: "checkmark.seal")
            } description: {
                Text(verbatim: emptyMessage)
            } actions: {
                Button("Close") { dismiss() }
                    .buttonStyle(.borderedProminent)
            }
        case .failed(let message):
            ContentUnavailableView {
                Label("Couldn't Load", systemImage: "exclamationmark.triangle")
            } description: {
                Text(verbatim: message)
            } actions: {
                Button("Try Again") {
                    Task {
                        if viewModel.session == nil {
                            await viewModel.start()
                        } else {
                            await viewModel.loadNext()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private var emptyMessage: String {
        switch viewModel.intent {
        case .learn:
            String(localized: "Nothing new to learn. Activate a concept to add new material.")
        case .scheduledReview:
            String(localized: "Nothing is due right now. Come back later.")
        default:
            String(localized: "No questions match this practice right now.")
        }
    }

    private func showSource(_ reference: SourceReference) {
        openSource = reference
    }
}

// MARK: - Introduction (LEARN)

private struct IntroductionView: View {
    let card: StudyCard
    let openSource: (SourceReference) -> Void
    let ready: () -> Void

    var body: some View {
        ScrollView {
            if let intro = card.introduction {
                VStack(alignment: .leading, spacing: 16) {
                    Text("New material")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                    Text(verbatim: intro.title)
                        .font(.title2.bold())
                    if !intro.objective.isEmpty {
                        Text(verbatim: intro.objective)
                            .foregroundStyle(.secondary)
                    }
                    Text(verbatim: intro.expectedKnowledge)
                        .font(.body)
                        .textSelection(.enabled)
                    if !intro.essentialPoints.isEmpty {
                        PointList(title: "Key points", systemImage: "list.bullet",
                                  points: intro.essentialPoints)
                    }
                    ForEach(intro.sources) { reference in
                        SourceRow(reference: reference, open: openSource)
                    }
                    Button(action: ready) {
                        Text("I'm ready: test me")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .accessibilityIdentifier("study.ready")
                }
                .padding()
            }
        }
    }
}

// MARK: - Answering

private struct AnswerView: View {
    let card: StudyCard
    @Bindable var viewModel: StudySessionViewModel
    @FocusState private var editorFocused: Bool

    private var isSubmitting: Bool {
        if case .submitting = viewModel.phase { return true }
        return false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(verbatim: card.conceptTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(verbatim: card.question.text)
                    .font(.title3.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                TextEditor(text: $viewModel.draft)
                    .focused($editorFocused)
                    .frame(minHeight: 180)
                    .padding(6)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
                    .disabled(isSubmitting)
                    .accessibilityLabel(Text("Your answer"))
                    .accessibilityIdentifier("study.answer")
                if isSubmitting {
                    ProgressView("Evaluating…")
                        .frame(maxWidth: .infinity)
                } else {
                    Button {
                        Task { await viewModel.submit() }
                    } label: {
                        Text("Submit")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!viewModel.canSubmit)
                    .accessibilityIdentifier("study.submit")
                    Button("Skip this question") {
                        Task { await viewModel.skip() }
                    }
                    .frame(maxWidth: .infinity)
                    .disabled(viewModel.isWorking)
                }
            }
            .padding()
        }
        .scrollDismissesKeyboard(.interactively)
    }
}

// MARK: - Result

private struct ResultView: View {
    let card: StudyCard
    let result: AnswerResult
    let viewModel: StudySessionViewModel
    let openSource: (SourceReference) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                OutcomeHeader(result: result)

                if let evaluation = result.evaluation {
                    EvaluationDetails(evaluation: evaluation)
                }

                ReferenceSection(reference: result.reference, openSource: openSource)

                ScheduleNote(result: result)

                if result.needsSelfGrade {
                    SelfGradeSection(result: result, viewModel: viewModel)
                } else {
                    Button {
                        Task { await viewModel.loadNext() }
                    } label: {
                        Text("Continue")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(viewModel.isWorking)
                    .accessibilityIdentifier("study.continue")

                    DisagreeMenu(result: result, viewModel: viewModel)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .overlay {
            if viewModel.isWorking {
                ProgressView()
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }
}

private struct OutcomeHeader: View {
    let result: AnswerResult

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let outcome = result.finalOutcome {
                Text(verbatim: outcome.label)
                    .font(.largeTitle.bold())
                    .foregroundStyle(outcome.color)
                if result.overrideOutcome != nil {
                    Text("Graded by you")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Needs your grade")
                    .font(.title.bold())
            }
            if let classification = result.evaluation?.classification {
                Text("Evaluation: \(classification.label)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("study.outcome")
    }
}

private struct EvaluationDetails: View {
    let evaluation: Evaluation

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            switch evaluation.status {
            case .failed, .notConfigured:
                Label {
                    Text(verbatim: evaluation.errorMessage
                        ?? String(localized: "The answer couldn't be evaluated."))
                } icon: {
                    Image(systemName: "exclamationmark.triangle")
                }
                .foregroundStyle(.orange)
            default:
                if !evaluation.feedback.isEmpty {
                    Text(verbatim: evaluation.feedback)
                }
                if evaluation.contextSufficient == false {
                    Label("The course material doesn't cover this well enough to grade it.",
                          systemImage: "questionmark.circle")
                        .foregroundStyle(.secondary)
                }
                if !evaluation.correctPoints.isEmpty {
                    PointList(title: "What you got right", systemImage: "checkmark.circle",
                              points: evaluation.correctPoints)
                }
                if !evaluation.missingPoints.isEmpty {
                    PointList(title: "What was missing", systemImage: "circle.dashed",
                              points: evaluation.missingPoints)
                }
                if !evaluation.misconceptions.isEmpty {
                    PointList(title: "Misconceptions", systemImage: "exclamationmark.circle",
                              points: evaluation.misconceptions)
                }
                if !evaluation.sourceCorrections.isEmpty {
                    PointList(title: "What the material says", systemImage: "book",
                              points: evaluation.sourceCorrections)
                }
            }
        }
    }
}

private struct ReferenceSection: View {
    let reference: Reference
    let openSource: (SourceReference) -> Void

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 10) {
                Text(verbatim: reference.expectedKnowledge)
                    .textSelection(.enabled)
                ForEach(reference.sources) { source in
                    SourceRow(reference: source, open: openSource)
                }
            }
            .padding(.top, 6)
        } label: {
            Label("Reference answer and sources", systemImage: "text.book.closed")
                .font(.headline)
        }
    }
}

private struct ScheduleNote: View {
    let result: AnswerResult

    var body: some View {
        Group {
            if let schedule = result.schedule {
                if schedule.nextState == .new {
                    Text("Not memorized yet: you'll see it again in this session.")
                } else if let due = schedule.nextDueAt {
                    Text("Next review: \(due.formatted(date: .abbreviated, time: .shortened))")
                }
            } else if result.intent == .practice, result.finalOutcome != nil {
                Text("Practice doesn't change your review schedule.")
            }
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
    }
}

private struct SelfGradeSection: View {
    let result: AnswerResult
    let viewModel: StudySessionViewModel

    private var canRetry: Bool {
        switch result.evaluation?.status {
        case .failed?, .notConfigured?: true
        default: false
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("How well did you know it?")
                .font(.headline)
            ForEach(ReviewOutcome.userGrades, id: \.self) { outcome in
                Button {
                    Task { await viewModel.override(with: outcome) }
                } label: {
                    HStack {
                        Text(verbatim: outcome.label).bold()
                        Spacer()
                        Text(verbatim: outcome.explanation)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(outcome.color)
                .disabled(viewModel.isWorking)
            }
            if canRetry {
                Button("Try the evaluation again") {
                    Task { await viewModel.retryEvaluation() }
                }
                .disabled(viewModel.isWorking)
            }
            Button("Skip for now") {
                Task { await viewModel.skip() }
            }
            .foregroundStyle(.secondary)
            .disabled(viewModel.isWorking)
        }
    }
}

/// "Disagree with the grade?" The backend keeps the AI's evaluation; the user's grade is stored
/// beside it and is what counts from now on.
private struct DisagreeMenu: View {
    let result: AnswerResult
    let viewModel: StudySessionViewModel

    var body: some View {
        Menu {
            ForEach(ReviewOutcome.userGrades.filter { $0 != result.finalOutcome }, id: \.self) {
                outcome in
                Button {
                    Task { await viewModel.override(with: outcome) }
                } label: {
                    Text("\(outcome.label): \(outcome.explanation)")
                }
            }
        } label: {
            Label("Disagree with the grade?", systemImage: "hand.raised")
                .frame(maxWidth: .infinity)
        }
        .disabled(viewModel.isWorking)
        .accessibilityIdentifier("study.disagree")
    }
}

// MARK: - Finished

private struct FinishedView: View {
    let viewModel: StudySessionViewModel
    let close: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Session Complete", systemImage: "checkmark.seal.fill")
        } description: {
            VStack(spacing: 6) {
                Text("Answered: \(viewModel.answeredCount)")
                ForEach(ReviewOutcome.userGrades, id: \.self) { outcome in
                    let count = viewModel.count(of: outcome)
                    if count > 0 {
                        Text(verbatim: "\(outcome.label): \(count)")
                    }
                }
            }
        } actions: {
            Button("Done", action: close)
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("study.done")
        }
    }
}

// MARK: - Shared

struct PointList: View {
    let title: LocalizedStringKey
    let systemImage: String
    let points: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: systemImage)
                .font(.headline)
            ForEach(points, id: \.self) { point in
                Text(verbatim: "• \(point)")
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
