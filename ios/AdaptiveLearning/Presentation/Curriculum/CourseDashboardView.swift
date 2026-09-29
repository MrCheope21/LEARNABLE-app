import SwiftUI

struct CourseDashboardView: View {
    @State private var viewModel: CourseDashboardViewModel
    let factory: ScreenFactory
    @State private var launch: StudyLaunch?

    init(viewModel: CourseDashboardViewModel, factory: ScreenFactory) {
        _viewModel = State(initialValue: viewModel)
        self.factory = factory
    }

    var body: some View {
        LoadableView(state: viewModel.state, retry: viewModel.load) { content in
            List {
                Section("Today") {
                    ReviewLoadRows(load: content.progress.reviewLoad)
                    StudyButtons(course: viewModel.course, load: content.progress.reviewLoad) {
                        launch = $0
                    }
                }
                Section("Curriculum") {
                    CurriculumProgressRows(curriculum: content.progress.curriculum)
                }
                Section("Memory") {
                    MemoryProgressRows(memory: content.progress.memory)
                }
                Section {
                    if content.chapters.isEmpty {
                        Text("Add a chapter, then add study material to it.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(content.chapters) { chapter in
                        NavigationLink(value: ChapterRoute(
                            course: viewModel.course, chapterId: chapter.id, title: chapter.title
                        )) {
                            ChapterRow(chapter: chapter,
                                       progress: content.progress.chapter(chapter.id))
                        }
                        .accessibilityIdentifier("chapter.row")
                    }
                    Button {
                        viewModel.isAddingChapter = true
                    } label: {
                        Label("Add Chapter", systemImage: "plus")
                    }
                } header: {
                    Text("Chapters")
                }
                Section {
                    NavigationLink(value: MaterialRoute(course: viewModel.course, chapterId: nil)) {
                        Label("All Study Material", systemImage: "doc.on.doc")
                    }
                }
            }
            .refreshable { await viewModel.load() }
        }
        .navigationTitle(Text(verbatim: viewModel.course.title))
        .task { await viewModel.load() }
        .errorAlert($viewModel.errorMessage)
        .sheet(isPresented: $viewModel.isAddingChapter) {
            AddChapterSheet(viewModel: viewModel)
        }
        .fullScreenCover(item: $launch, onDismiss: {
            Task { await viewModel.load() }
        }) { launch in
            StudySessionView(viewModel: factory.session(launch), factory: factory)
        }
    }
}

private struct ChapterRow: View {
    let chapter: ChapterNode
    let progress: ChapterProgress?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(verbatim: chapter.title)
                .font(.headline)
            if let progress {
                Text("\(progress.curriculum.active) of \(progress.curriculum.concepts) concepts active · mastery \(percentText(progress.memory.mastery))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        // No .accessibilityElement: only shown inside a NavigationLink, which already merges
        // its label into one activatable element (a nested one shadows it).
    }
}

/// Start Review / Continue Learning / Practice hard questions for one Course.
struct StudyButtons: View {
    let course: Course
    let load: ReviewLoad
    let start: (StudyLaunch) -> Void

    var body: some View {
        Button {
            start(StudyLaunch(courseId: course.id, courseTitle: course.title,
                              request: .scheduledReview))
        } label: {
            Label("Start Review", systemImage: "arrow.triangle.2.circlepath")
        }
        .disabled(load.dueNow == 0)
        Button {
            start(StudyLaunch(courseId: course.id, courseTitle: course.title, request: .learn()))
        } label: {
            Label("Continue Learning", systemImage: "sparkles")
        }
        .disabled(load.newToLearn == 0)
        Button {
            start(StudyLaunch(courseId: course.id, courseTitle: course.title,
                              request: .practiceHard))
        } label: {
            Label("Practice Hard Questions", systemImage: "flame")
        }
    }
}

private struct AddChapterSheet: View {
    @Bindable var viewModel: CourseDashboardViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                TextField("Chapter title", text: $viewModel.newChapterTitle)
            }
            .navigationTitle("New Chapter")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        Task {
                            if await viewModel.addChapter() { dismiss() }
                        }
                    }
                    .disabled(viewModel.newChapterTitle
                        .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
