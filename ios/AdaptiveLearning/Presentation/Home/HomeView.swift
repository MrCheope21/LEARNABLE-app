import SwiftUI

/// Home: what to do today, with one clear primary action. Not a chat.
struct HomeView: View {
    @Bindable var viewModel: HomeViewModel
    let factory: ScreenFactory
    @State private var launch: StudyLaunch?

    var body: some View {
        NavigationStack {
            LoadableView(state: viewModel.state, retry: viewModel.load) { summary in
                if summary.courses.isEmpty {
                    ContentUnavailableView {
                        Label("No Courses Yet", systemImage: "books.vertical")
                    } description: {
                        Text("Create a course in the Courses tab to get started.")
                    }
                } else {
                    content(summary)
                }
            }
            .navigationTitle("Home")
            .task { await viewModel.load() }
            .errorAlert($viewModel.errorMessage)
            .fullScreenCover(item: $launch, onDismiss: {
                Task { await viewModel.load() }
            }) { launch in
                StudySessionView(viewModel: factory.session(launch), factory: factory)
            }
        }
    }

    private func content(_ summary: HomeSummary) -> some View {
        List {
            Section {
                ReviewLoadRows(load: summary.totals)
                if let review = viewModel.reviewLaunch {
                    Button {
                        launch = review
                    } label: {
                        Text("Start Review")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
                if let learn = viewModel.learnLaunch {
                    Button {
                        launch = learn
                    } label: {
                        Text("Continue Learning")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
                if viewModel.reviewLaunch == nil && viewModel.learnLaunch == nil {
                    Text("You're all caught up.")
                        .foregroundStyle(.secondary)
                }
            } header: {
                Text("Today")
            }

            let weak = summary.courses.flatMap { course in
                course.weakConcepts.map { WeakEntry(courseTitle: course.title, concept: $0) }
            }
            if !weak.isEmpty {
                Section("Weak Areas") {
                    ForEach(weak) { entry in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: entry.concept.title)
                            Text(verbatim: entry.courseTitle)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
            }

            Section("Your Courses") {
                ForEach(summary.courses) { course in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(verbatim: course.title)
                            .font(.headline)
                        Text("Due: \(course.reviewLoad.dueNow) · New: \(course.reviewLoad.newToLearn) · Active concepts: \(course.activeConcepts)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Mastery (estimate): \(percentText(course.mastery))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .refreshable { await viewModel.load() }
    }
}

private struct WeakEntry: Identifiable {
    let courseTitle: String
    let concept: WeakConcept

    var id: UUID { concept.id }
}
