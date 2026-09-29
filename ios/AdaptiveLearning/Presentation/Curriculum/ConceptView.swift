import SwiftUI

struct ConceptView: View {
    @State private var viewModel: ConceptViewModel
    @Environment(\.screenFactory) private var factory
    @State private var launch: StudyLaunch?
    @State private var selectedItem: LearningItem?

    init(viewModel: ConceptViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        LoadableView(state: viewModel.state, retry: viewModel.load) { content in
            List {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: content.concept.title)
                            .font(.title3.bold())
                        if !content.concept.description.isEmpty {
                            Text(verbatim: content.concept.description)
                                .foregroundStyle(.secondary)
                        }
                        Text(verbatim: content.concept.studyState.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(content.concept.studyState == .active
                                ? .green : .secondary)
                    }
                    if content.concept.needsSourceReview {
                        Label("The material this concept came from was deleted. Keep, edit or delete it.",
                              systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                }

                Section {
                    ConceptActions(concept: content.concept, viewModel: viewModel)
                    if viewModel.itemsToLearn > 0 {
                        Button {
                            launch = StudyLaunch(
                                courseId: viewModel.route.course.id,
                                courseTitle: viewModel.route.course.title,
                                request: .learn(conceptIds: [content.concept.id])
                            )
                        } label: {
                            Label("Learn Now (\(viewModel.itemsToLearn))", systemImage: "sparkles")
                        }
                        .accessibilityIdentifier("concept.learnNow")
                    }
                }

                GenerationStatusSection(concept: content.concept, viewModel: viewModel)

                if let progress = content.progress, progress.memory.itemsTrained > 0 {
                    Section("Memory") {
                        MemoryProgressRows(memory: progress.memory)
                    }
                }

                if !content.items.isEmpty {
                    Section("Learning Items") {
                        ForEach(content.items) { item in
                            Button {
                                selectedItem = item
                            } label: {
                                LearningItemRow(item: item)
                            }
                            .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .refreshable { await viewModel.load() }
        }
        .navigationTitle(Text(verbatim: viewModel.route.title))
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if viewModel.isWorking {
                ProgressView()
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .task { await viewModel.load() }
        .errorAlert($viewModel.errorMessage)
        .sheet(item: $selectedItem) { item in
            LearningItemDetailView(item: item, viewModel: viewModel)
        }
        .fullScreenCover(item: $launch, onDismiss: {
            Task { await viewModel.load() }
        }) { launch in
            if let factory {
                StudySessionView(viewModel: factory.session(launch), factory: factory)
            }
        }
    }
}

/// Activation controls: only the transitions the backend allows from the current state.
private struct ConceptActions: View {
    let concept: Concept
    let viewModel: ConceptViewModel

    var body: some View {
        switch concept.studyState {
        case .notStudied, .studied, .completed:
            Button {
                Task { await viewModel.perform(.activate) }
            } label: {
                Label("Activate", systemImage: "bolt.fill")
            }
            .accessibilityIdentifier("concept.activate")
            .disabled(viewModel.isWorking)
            if concept.studyState == .notStudied {
                Button {
                    Task { await viewModel.perform(.markStudied) }
                } label: {
                    Label("Mark as Studied", systemImage: "book")
                }
                .disabled(viewModel.isWorking)
            }
        case .active:
            Button {
                Task { await viewModel.perform(.pause) }
            } label: {
                Label("Pause", systemImage: "pause.circle")
            }
            .disabled(viewModel.isWorking)
            Button {
                Task { await viewModel.perform(.deactivate) }
            } label: {
                Label("Deactivate", systemImage: "stop.circle")
            }
            .disabled(viewModel.isWorking)
        case .paused:
            Button {
                Task { await viewModel.perform(.resume) }
            } label: {
                Label("Resume", systemImage: "play.circle")
            }
            .disabled(viewModel.isWorking)
            Button {
                Task { await viewModel.perform(.deactivate) }
            } label: {
                Label("Deactivate", systemImage: "stop.circle")
            }
            .disabled(viewModel.isWorking)
        case .unknown:
            EmptyView()
        }
    }
}

private struct GenerationStatusSection: View {
    let concept: Concept
    let viewModel: ConceptViewModel

    var body: some View {
        switch concept.itemGenerationStatus {
        case .generating:
            Section {
                HStack(spacing: 10) {
                    ProgressView()
                    Text("Preparing learning items…")
                }
            }
        case .failed, .insufficientContext:
            Section {
                Text(verbatim: concept.itemGenerationError
                    ?? String(localized: "Learning items couldn't be prepared."))
                    .foregroundStyle(.secondary)
                Button("Try Again") {
                    Task { await viewModel.generateItems() }
                }
                .disabled(viewModel.isWorking)
            }
        default:
            EmptyView()
        }
    }
}

private struct LearningItemRow: View {
    let item: LearningItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(verbatim: item.title)
                .font(.headline)
            HStack(spacing: 8) {
                Text(verbatim: item.role.label)
                Text(verbatim: "·")
                Text(verbatim: item.reviewState.state.label)
                if item.reviewState.level > 0 {
                    Text("Level \(item.reviewState.level)")
                }
                if item.reviewState.markedHard {
                    Image(systemName: "flame")
                        .foregroundStyle(.orange)
                        .accessibilityLabel(Text("Marked hard"))
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            if !item.inTraining {
                Text("Not in training")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        // No .accessibilityElement: shown inside a Button, which already merges its label into
        // one activatable element (a nested one shadows it).
    }
}

/// A Learning Item's content, memory state, questions and sources.
private struct LearningItemDetailView: View {
    let item: LearningItem
    let viewModel: ConceptViewModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.screenFactory) private var factory
    @State private var inTraining: Bool

    init(item: LearningItem, viewModel: ConceptViewModel) {
        self.item = item
        self.viewModel = viewModel
        _inTraining = State(initialValue: item.inTraining)
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if !item.objective.isEmpty {
                        Text(verbatim: item.objective)
                            .foregroundStyle(.secondary)
                    }
                    Text(verbatim: item.expectedKnowledge)
                        .textSelection(.enabled)
                }
                if !item.essentialPoints.isEmpty {
                    Section("Key points") {
                        ForEach(item.essentialPoints, id: \.self) { point in
                            Text(verbatim: point)
                        }
                    }
                }
                Section("Memory") {
                    LabeledContent("State") {
                        Text(verbatim: item.reviewState.state.label)
                    }
                    LabeledContent("Level") {
                        Text(item.reviewState.level, format: .number)
                    }
                    if let due = item.reviewState.dueAt {
                        LabeledContent("Next review") {
                            Text(due.formatted(date: .abbreviated, time: .shortened))
                        }
                    }
                    LabeledContent("Reviews") {
                        Text(item.reviewState.reviewCount, format: .number)
                    }
                    LabeledContent("Lapses") {
                        Text(item.reviewState.lapseCount, format: .number)
                    }
                    Toggle("In training", isOn: $inTraining)
                        .onChange(of: inTraining) { _, newValue in
                            Task { await viewModel.setInTraining(newValue, item: item) }
                        }
                }
                Section("Questions") {
                    ForEach(item.questions) { question in
                        Text(verbatim: question.text)
                    }
                }
                if let factory {
                    ItemSourcesSection(itemId: item.id, factory: factory)
                }
            }
            .navigationTitle(Text(verbatim: item.title))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

/// The passages an item was generated from ("View source").
private struct ItemSourcesSection: View {
    let itemId: UUID
    let factory: ScreenFactory
    @State private var passages: Loadable<[SourcePassage]> = .loading

    var body: some View {
        Section("Sources") {
            switch passages {
            case .loading:
                ProgressView()
            case .failed(let message):
                Text(verbatim: message)
                    .foregroundStyle(.secondary)
            case .loaded(let list):
                if list.isEmpty {
                    Text("No source passages.")
                        .foregroundStyle(.secondary)
                }
                ForEach(list) { passage in
                    VStack(alignment: .leading, spacing: 4) {
                        if let page = passage.pageNumber {
                            Text("Page \(page)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let section = passage.section {
                            Text(verbatim: section)
                                .font(.caption.weight(.semibold))
                        }
                        Text(verbatim: passage.text)
                            .font(.callout)
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .task {
            do {
                passages = .loaded(try await factory.concepts.fetchItemSources(itemId: itemId))
            } catch is CancellationError {
                return
            } catch {
                passages = .failed(userMessage(for: error))
            }
        }
    }
}
