import Foundation
import Observation

/// A Course's home: progress, today's reviews and its Chapters (docs/PROJECT_SPEC.md §54, §63).
@MainActor
@Observable
final class CourseDashboardViewModel {
    struct Content {
        var chapters: [ChapterNode]
        var progress: CourseProgress
    }

    let course: Course
    private(set) var state: Loadable<Content> = .loading
    var errorMessage: String?
    var isAddingChapter = false
    var newChapterTitle = ""

    private let courses: CourseRepository
    private let progress: ProgressRepository

    init(course: Course, courses: CourseRepository, progress: ProgressRepository) {
        self.course = course
        self.courses = courses
        self.progress = progress
    }

    func load() async {
        do {
            let chapters = try await courses.fetchOutline(courseId: course.id)
            let courseProgress = try await progress.fetchProgress(courseId: course.id)
            state = .loaded(Content(chapters: chapters, progress: courseProgress))
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

    /// Returns true when the Chapter was created, so the sheet can close.
    func addChapter() async -> Bool {
        let title = newChapterTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return false }
        do {
            try await courses.createChapter(courseId: course.id, title: title)
            newChapterTitle = ""
            await load()
            return true
        } catch is CancellationError {
            return false
        } catch {
            errorMessage = userMessage(for: error)
            return false
        }
    }
}
