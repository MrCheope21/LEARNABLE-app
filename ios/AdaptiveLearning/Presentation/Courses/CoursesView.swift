import SwiftUI

struct CoursesView: View {
    @Bindable var viewModel: CoursesViewModel
    let factory: ScreenFactory

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.courses.isEmpty && viewModel.hasLoaded {
                    ContentUnavailableView {
                        Label("No Courses Yet", systemImage: "books.vertical")
                    } description: {
                        Text("Create a course to start building your curriculum.")
                    } actions: {
                        Button("New Course") { viewModel.isShowingNewCourse = true }
                            .buttonStyle(.borderedProminent)
                    }
                } else {
                    List(viewModel.courses) { course in
                        NavigationLink(value: course) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(verbatim: course.title)
                                    .font(.headline)
                                if !course.description.isEmpty {
                                    Text(verbatim: course.description)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                            }
                        }
                        .accessibilityIdentifier("course.row")
                    }
                }
            }
            .overlay {
                if viewModel.isLoading && !viewModel.hasLoaded {
                    ProgressView()
                }
            }
            .navigationTitle("Courses")
            // Course → Chapter → Topic → Concept, plus material and passages.
            .navigationDestination(for: Course.self) { course in
                CourseDashboardView(viewModel: factory.dashboard(for: course), factory: factory)
            }
            .navigationDestination(for: ChapterRoute.self) { route in
                ChapterView(viewModel: factory.chapter(route))
            }
            .navigationDestination(for: TopicRoute.self) { route in
                TopicView(viewModel: factory.topic(route))
            }
            .navigationDestination(for: ConceptRoute.self) { route in
                ConceptView(viewModel: factory.concept(route))
            }
            .navigationDestination(for: MaterialRoute.self) { route in
                CourseDetailView(viewModel: factory.material(route))
            }
            .navigationDestination(for: CourseDocument.self) { document in
                SourcePassagesView(viewModel: factory.passages(for: document))
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        viewModel.isShowingNewCourse = true
                    } label: {
                        Label("New Course", systemImage: "plus")
                    }
                }
            }
            .sheet(isPresented: $viewModel.isShowingNewCourse) {
                NewCourseView(viewModel: viewModel)
            }
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .errorAlert($viewModel.errorMessage)
        }
    }
}
