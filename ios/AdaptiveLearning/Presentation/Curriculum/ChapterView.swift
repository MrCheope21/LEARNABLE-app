import SwiftUI

struct ChapterView: View {
    @State private var viewModel: ChapterViewModel

    init(viewModel: ChapterViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        LoadableView(state: viewModel.state, retry: viewModel.load) { content in
            List {
                if let progress = content.progress {
                    Section("Curriculum") {
                        CurriculumProgressRows(curriculum: progress.curriculum)
                    }
                    Section("Memory") {
                        MemoryProgressRows(memory: progress.memory)
                    }
                }
                Section {
                    if content.chapter.topics.isEmpty {
                        Text("No topics yet. Add study material to this chapter, then analyze it.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(content.chapter.topics) { topic in
                        NavigationLink(value: TopicRoute(
                            course: viewModel.route.course, topicId: topic.id, title: topic.title
                        )) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(verbatim: topic.title)
                                    .font(.headline)
                                let active = topic.concepts.filter { $0.studyState == .active }.count
                                Text("\(active) of \(topic.concepts.count) concepts active")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .accessibilityIdentifier("topic.row")
                    }
                } header: {
                    Text("Topics")
                }
                Section {
                    NavigationLink(value: MaterialRoute(
                        course: viewModel.route.course, chapterId: viewModel.route.chapterId
                    )) {
                        Label("Chapter Material", systemImage: "doc.on.doc")
                    }
                    Button {
                        Task { await viewModel.analyzeNewMaterial() }
                    } label: {
                        HStack {
                            Label("Analyze New Material", systemImage: "wand.and.stars")
                            if viewModel.isAnalyzing {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(viewModel.isAnalyzing)
                } footer: {
                    Text("The AI proposes topics and concepts from material not analyzed yet. You review the proposal before anything changes.")
                }
            }
            .refreshable { await viewModel.load() }
        }
        .navigationTitle(Text(verbatim: viewModel.route.title))
        .navigationDestination(item: $viewModel.openProposal) { route in
            ProposalDestination(route: route)
        }
        .onChange(of: viewModel.openProposal) { _, route in
            // Back from reviewing a proposal: it may have added Topics.
            if route == nil {
                Task { await viewModel.load() }
            }
        }
        .task { await viewModel.load() }
        .errorAlert($viewModel.errorMessage)
    }
}

/// Resolved by the Courses stack's factory (see CoursesView).
struct ProposalDestination: View {
    let route: ProposalRoute
    @Environment(\.screenFactory) private var factory

    var body: some View {
        if let factory {
            ProposalReviewView(viewModel: factory.proposal(route))
        }
    }
}
