import Foundation
import Observation

/// One Chapter: its Topics, progress, material, and analyzing new material into a curriculum
/// proposal (docs/API.md "AI curriculum generation": Chapter scope).
@MainActor
@Observable
final class ChapterViewModel {
    struct Content {
        var chapter: ChapterNode
        var progress: ChapterProgress?
    }

    let route: ChapterRoute
    private(set) var state: Loadable<Content> = .loading
    private(set) var isAnalyzing = false
    /// Set when a proposal was created: the view navigates to its review.
    var openProposal: ProposalRoute?
    var errorMessage: String?

    private let courses: CourseRepository
    private let progress: ProgressRepository
    private let curriculum: CurriculumRepository

    init(
        route: ChapterRoute,
        courses: CourseRepository,
        progress: ProgressRepository,
        curriculum: CurriculumRepository
    ) {
        self.route = route
        self.courses = courses
        self.progress = progress
        self.curriculum = curriculum
    }

    func load() async {
        do {
            let outline = try await courses.fetchOutline(courseId: route.course.id)
            guard let chapter = outline.first(where: { $0.id == route.chapterId }) else {
                state = .failed(String(localized: "This item no longer exists."))
                return
            }
            let courseProgress = try await progress.fetchProgress(courseId: route.course.id)
            state = .loaded(Content(chapter: chapter, progress: courseProgress.chapter(chapter.id)))
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

    /// Asks the AI to propose Topics and Concepts from this Chapter's material that hasn't been
    /// analyzed yet. Nothing changes until the user applies the proposal.
    func analyzeNewMaterial() async {
        isAnalyzing = true
        defer { isAnalyzing = false }
        do {
            let proposal = try await curriculum.generateProposal(
                courseId: route.course.id, chapterId: route.chapterId
            )
            openProposal = ProposalRoute(course: route.course, proposalId: proposal.id)
        } catch is CancellationError {
            return
        } catch APIError.server(409, _, _) {
            errorMessage = String(
                localized: "There's no new study material to analyze in this chapter. Add material first."
            )
        } catch {
            errorMessage = userMessage(for: error)
        }
    }
}
