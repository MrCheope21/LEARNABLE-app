import SwiftUI

/// The AI's proposed curriculum, editable before anything reaches the Course
/// (docs/PROJECT_SPEC.md §20): rename, delete, reorder, add, then accept or reject.
struct ProposalReviewView: View {
    @State private var viewModel: ProposalReviewViewModel
    @Environment(\.dismiss) private var dismiss

    init(viewModel: ProposalReviewViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        LoadableView(state: viewModel.state, retry: viewModel.load) { proposal in
            switch proposal.status {
            case .generating:
                VStack(spacing: 12) {
                    ProgressView()
                    Text("The AI is reading your material…")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .ready:
                editor(proposal)
            case .applied:
                ContentUnavailableView("Already Applied", systemImage: "checkmark.seal")
            default:
                ContentUnavailableView {
                    Label("No Proposal", systemImage: "doc.questionmark")
                } description: {
                    Text(verbatim: proposal.errorMessage
                        ?? String(localized: "The AI couldn't propose a curriculum."))
                }
            }
        }
        .navigationTitle("Proposed Curriculum")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load() }
        .errorAlert($viewModel.errorMessage)
        .onChange(of: viewModel.isFinished) { _, finished in
            if finished { dismiss() }
        }
    }

    private func editor(_ proposal: CurriculumProposal) -> some View {
        List {
            Section {
                if proposal.passagesUsed < proposal.passagesTotal {
                    Label("The material was long: this covers its first \(proposal.passagesUsed) of \(proposal.passagesTotal) passages.",
                          systemImage: "info.circle")
                        .font(.footnote)
                }
                if proposal.droppedConcepts > 0 {
                    Label("\(proposal.droppedConcepts) proposed concepts were left out because they couldn't be tied to your material.",
                          systemImage: "info.circle")
                        .font(.footnote)
                }
                Text("Edit anything below. Nothing is activated: you choose what to study afterwards.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if viewModel.isChapterScope {
                ForEach($viewModel.topics) { $topic in
                    TopicEditor(topic: $topic, viewModel: viewModel)
                }
            } else {
                ForEach($viewModel.chapters) { $chapter in
                    ChapterEditor(chapter: $chapter, viewModel: viewModel)
                }
            }
            Section {
                Button {
                    Task { await viewModel.apply() }
                } label: {
                    Text("Accept Curriculum")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.isSubmitting || viewModel.isEmpty)
                Button("Reject Proposal", role: .destructive) {
                    Task { await viewModel.reject() }
                }
                .frame(maxWidth: .infinity)
                .disabled(viewModel.isSubmitting)
            }
        }
        .environment(\.editMode, .constant(.active))
    }
}

private struct TopicEditor: View {
    @Binding var topic: ProposalReviewViewModel.DraftTopic
    let viewModel: ProposalReviewViewModel

    var body: some View {
        Section {
            ForEach($topic.concepts) { $concept in
                HStack {
                    TextField("Concept title", text: $concept.title)
                    if concept.existingConceptId != nil {
                        Text("Already exists")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .onDelete { offsets in
                topic.concepts.remove(atOffsets: offsets)
            }
            .onMove { source, destination in
                topic.concepts.move(fromOffsets: source, toOffset: destination)
            }
            Button {
                viewModel.addConcept(to: topic)
            } label: {
                Label("Add Concept", systemImage: "plus")
            }
        } header: {
            HStack {
                if topic.existingTopicId != nil {
                    Text(verbatim: topic.title)
                    Text("(existing topic)")
                } else {
                    TextField("Topic title", text: $topic.title)
                }
                Spacer()
                Button(role: .destructive) {
                    viewModel.deleteTopic(topic)
                } label: {
                    Image(systemName: "trash")
                }
                .accessibilityLabel(Text("Delete topic"))
            }
            .textCase(nil)
        }
    }
}

private struct ChapterEditor: View {
    @Binding var chapter: ProposalReviewViewModel.DraftChapter
    let viewModel: ProposalReviewViewModel

    var body: some View {
        Section {
            ForEach($chapter.topics) { $topic in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        TextField("Topic title", text: $topic.title)
                            .font(.headline)
                        Button(role: .destructive) {
                            viewModel.deleteTopic(topic, from: chapter)
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel(Text("Delete topic"))
                    }
                    ForEach($topic.concepts) { $concept in
                        HStack {
                            TextField("Concept title", text: $concept.title)
                                .padding(.leading, 12)
                            Button(role: .destructive) {
                                topic.concepts.removeAll { $0.id == concept.id }
                            } label: {
                                Image(systemName: "minus.circle")
                            }
                            .buttonStyle(.borderless)
                            .accessibilityLabel(Text("Delete concept"))
                        }
                    }
                }
            }
        } header: {
            HStack {
                TextField("Chapter title", text: $chapter.title)
                Spacer()
                Button(role: .destructive) {
                    viewModel.deleteChapter(chapter)
                } label: {
                    Image(systemName: "trash")
                }
                .accessibilityLabel(Text("Delete chapter"))
            }
            .textCase(nil)
        }
    }
}
