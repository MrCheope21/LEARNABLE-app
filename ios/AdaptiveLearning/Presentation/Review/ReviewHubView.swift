import SwiftUI

/// The Review tab: start a session in any Course. Scheduled review is the default; learning new
/// material and practising hard questions are separate, explicit choices.
struct ReviewHubView: View {
    @Bindable var viewModel: HomeViewModel
    let factory: ScreenFactory
    @State private var launch: StudyLaunch?

    var body: some View {
        NavigationStack {
            LoadableView(state: viewModel.state, retry: viewModel.load) { summary in
                if summary.courses.isEmpty {
                    ContentUnavailableView {
                        Label("Nothing to Review", systemImage: "checkmark.circle")
                    } description: {
                        Text("Create a course and activate some concepts first.")
                    }
                } else {
                    List(summary.courses) { course in
                        Section {
                            StudyButtons(
                                course: Course(id: course.courseId, title: course.title,
                                               description: "", language: ""),
                                load: course.reviewLoad
                            ) { launch = $0 }
                        } header: {
                            Text(verbatim: course.title)
                        } footer: {
                            Text("Due now: \(course.reviewLoad.dueNow) · New to learn: \(course.reviewLoad.newToLearn)")
                        }
                    }
                    .refreshable { await viewModel.load() }
                }
            }
            .navigationTitle("Review")
            .task { await viewModel.load() }
            .errorAlert($viewModel.errorMessage)
            .fullScreenCover(item: $launch, onDismiss: {
                Task { await viewModel.load() }
            }) { launch in
                StudySessionView(viewModel: factory.session(launch), factory: factory)
            }
        }
    }
}
