import Foundation
import Observation

/// The Progress tab: one Course at a time, curriculum and memory progress kept separate
/// (docs/PROJECT_SPEC.md §54, §67). Named `ProgressDashboard...` to avoid colliding with
/// SwiftUI's `ProgressView`.
@MainActor
@Observable
final class ProgressDashboardViewModel {
    private(set) var courses: Loadable<[CourseSummary]> = .loading
    private(set) var selectedCourseId: UUID?
    private(set) var progress: Loadable<CourseProgress> = .loading
    var errorMessage: String?

    private let repository: ProgressRepository

    init(repository: ProgressRepository) {
        self.repository = repository
    }

    var selectedCourse: CourseSummary? {
        courses.value?.first { $0.courseId == selectedCourseId }
    }

    func load() async {
        do {
            let summaries = try await repository.fetchHome().courses
            courses = .loaded(summaries)
            if selectedCourseId == nil || !summaries.contains(where: { $0.courseId == selectedCourseId }) {
                selectedCourseId = summaries.first?.courseId
            }
        } catch is CancellationError {
            return
        } catch {
            if courses.value == nil {
                courses = .failed(userMessage(for: error))
            } else {
                errorMessage = userMessage(for: error)
            }
            return
        }
        await loadProgress()
    }

    func select(_ courseId: UUID) async {
        guard courseId != selectedCourseId else { return }
        selectedCourseId = courseId
        progress = .loading
        await loadProgress()
    }

    func loadProgress() async {
        guard let selectedCourseId else { return }
        do {
            progress = .loaded(try await repository.fetchProgress(courseId: selectedCourseId))
        } catch is CancellationError {
            return
        } catch {
            if progress.value == nil {
                progress = .failed(userMessage(for: error))
            } else {
                errorMessage = userMessage(for: error)
            }
        }
    }
}
