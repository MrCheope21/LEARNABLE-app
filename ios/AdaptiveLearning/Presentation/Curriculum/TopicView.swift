import SwiftUI

struct TopicView: View {
    @State private var viewModel: TopicViewModel

    init(viewModel: TopicViewModel) {
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
                Section("Concepts") {
                    if content.topic.concepts.isEmpty {
                        Text("No concepts in this topic.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(content.topic.concepts) { concept in
                        NavigationLink(value: ConceptRoute(
                            course: viewModel.route.course,
                            conceptId: concept.id,
                            title: concept.title
                        )) {
                            ConceptRow(concept: concept, mastery: viewModel.mastery(of: concept))
                        }
                        .accessibilityIdentifier("concept.row")
                    }
                }
            }
            .refreshable { await viewModel.load() }
        }
        .navigationTitle(Text(verbatim: viewModel.route.title))
        .task { await viewModel.load() }
        .errorAlert($viewModel.errorMessage)
    }
}

private struct ConceptRow: View {
    let concept: Concept
    let mastery: Double?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(verbatim: concept.title)
                    .font(.headline)
                Text(verbatim: concept.studyState.label)
                    .font(.caption)
                    .foregroundStyle(concept.studyState == .active ? .green : .secondary)
            }
            Spacer()
            if concept.needsSourceReview {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
                    .accessibilityLabel(Text("Needs source review"))
            }
            if concept.studyState == .active {
                Text(verbatim: percentText(mastery))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .accessibilityLabel(Text("Mastery \(percentText(mastery))"))
            }
        }
        // No .accessibilityElement: only shown inside a NavigationLink, which already merges
        // its label into one activatable element (a nested one shadows it).
    }
}
