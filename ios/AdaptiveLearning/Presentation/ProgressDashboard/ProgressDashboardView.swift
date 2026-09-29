import SwiftUI

/// Curriculum and memory progress side by side but never merged into one score
/// (docs/PROJECT_SPEC.md §54, §67).
struct ProgressDashboardView: View {
    @Bindable var viewModel: ProgressDashboardViewModel

    var body: some View {
        NavigationStack {
            LoadableView(state: viewModel.courses, retry: viewModel.load) { courses in
                if courses.isEmpty {
                    ContentUnavailableView {
                        Label("No Progress Yet", systemImage: "chart.line.uptrend.xyaxis")
                    } description: {
                        Text("Create a course and start learning to see your progress.")
                    }
                } else {
                    List {
                        if courses.count > 1 {
                            Section {
                                Picker("Course", selection: Binding(
                                    get: { viewModel.selectedCourseId ?? courses[0].courseId },
                                    set: { id in Task { await viewModel.select(id) } }
                                )) {
                                    ForEach(courses) { course in
                                        Text(verbatim: course.title).tag(course.courseId)
                                    }
                                }
                            }
                        }
                        CourseProgressSections(
                            state: viewModel.progress,
                            weak: viewModel.selectedCourse?.weakConcepts ?? [],
                            retry: viewModel.loadProgress
                        )
                    }
                    .refreshable { await viewModel.load() }
                }
            }
            .navigationTitle("Progress")
            .task { await viewModel.load() }
            .errorAlert($viewModel.errorMessage)
        }
    }
}

private struct CourseProgressSections: View {
    let state: Loadable<CourseProgress>
    let weak: [WeakConcept]
    let retry: () async -> Void

    var body: some View {
        switch state {
        case .loading:
            Section {
                ProgressView()
                    .frame(maxWidth: .infinity)
            }
        case .failed(let message):
            Section {
                Text(verbatim: message)
                    .foregroundStyle(.secondary)
                Button("Try Again") {
                    Task { await retry() }
                }
            }
        case .loaded(let progress):
            Section("Upcoming Reviews") {
                ReviewLoadRows(load: progress.reviewLoad)
            }
            Section {
                CurriculumProgressRows(curriculum: progress.curriculum)
            } header: {
                Text("Curriculum Progress")
            } footer: {
                Text("How much of the material you have studied and activated.")
            }
            Section {
                MemoryProgressRows(memory: progress.memory)
            } header: {
                Text("Memory Progress")
            } footer: {
                Text("How well you retain what you train. Mastery is an estimate from your reviews, not a measurement.")
            }
            if !weak.isEmpty {
                Section("Weak Concepts") {
                    ForEach(weak) { concept in
                        LabeledContent {
                            Text("Lapses: \(concept.lapses)")
                        } label: {
                            Text(verbatim: concept.title)
                        }
                    }
                }
            }
            Section("Chapters") {
                ForEach(progress.chapters) { chapter in
                    DisclosureGroup {
                        ForEach(chapter.topics) { topic in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: topic.title)
                                Text("\(topic.curriculum.active) of \(topic.curriculum.concepts) concepts active · mastery \(percentText(topic.memory.mastery))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .accessibilityElement(children: .combine)
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: chapter.title)
                                .font(.headline)
                            Text("\(chapter.curriculum.active) of \(chapter.curriculum.concepts) concepts active · mastery \(percentText(chapter.memory.mastery))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        // No .accessibilityElement: the DisclosureGroup label is the tappable
                        // toggle and already merges its content (a nested one shadows it).
                    }
                }
            }
        }
    }
}
