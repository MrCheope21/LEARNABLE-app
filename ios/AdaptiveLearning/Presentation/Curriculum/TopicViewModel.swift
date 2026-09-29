import Foundation
import Observation

/// One Topic: its Concepts with their study state and mastery.
@MainActor
@Observable
final class TopicViewModel {
    struct Content {
        var topic: TopicNode
        var progress: TopicProgress?
    }

    let route: TopicRoute
    private(set) var state: Loadable<Content> = .loading
    var errorMessage: String?

    private let courses: CourseRepository
    private let progress: ProgressRepository

    init(route: TopicRoute, courses: CourseRepository, progress: ProgressRepository) {
        self.route = route
        self.courses = courses
        self.progress = progress
    }

    func load() async {
        do {
            let outline = try await courses.fetchOutline(courseId: route.course.id)
            guard let topic = outline.flatMap(\.topics).first(where: { $0.id == route.topicId })
            else {
                state = .failed(String(localized: "This item no longer exists."))
                return
            }
            let courseProgress = try await progress.fetchProgress(courseId: route.course.id)
            state = .loaded(Content(topic: topic, progress: courseProgress.topic(topic.id)))
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

    func mastery(of concept: Concept) -> Double? {
        state.value?.progress?.concepts.first { $0.id == concept.id }?.memory.mastery
    }
}
