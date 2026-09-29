import Foundation
import Observation

/// Today's work across the user's Courses (docs/PROJECT_SPEC.md §64), from `GET /api/v1/home`.
/// Used by Home and by the Review tab.
@MainActor
@Observable
final class HomeViewModel {
    private(set) var state: Loadable<HomeSummary> = .loading
    var errorMessage: String?

    private let progress: ProgressRepository

    init(progress: ProgressRepository) {
        self.progress = progress
    }

    func load() async {
        do {
            state = .loaded(try await progress.fetchHome())
        } catch is CancellationError {
            return
        } catch {
            if state.value == nil {
                state = .failed(userMessage(for: error))
            } else {
                errorMessage = userMessage(for: error)
            }
        }
    }

    /// Reviews in the Course with the most due now; nil when nothing is due anywhere.
    var reviewLaunch: StudyLaunch? {
        guard let course = state.value?.courses
            .filter({ $0.reviewLoad.dueNow > 0 })
            .max(by: { $0.reviewLoad.dueNow < $1.reviewLoad.dueNow })
        else { return nil }
        return StudyLaunch(courseId: course.courseId, courseTitle: course.title,
                           request: .scheduledReview)
    }

    /// New material in the Course with the most waiting; nil when there is none.
    var learnLaunch: StudyLaunch? {
        guard let course = state.value?.courses
            .filter({ $0.reviewLoad.newToLearn > 0 })
            .max(by: { $0.reviewLoad.newToLearn < $1.reviewLoad.newToLearn })
        else { return nil }
        return StudyLaunch(courseId: course.courseId, courseTitle: course.title,
                           request: .learn())
    }
}
