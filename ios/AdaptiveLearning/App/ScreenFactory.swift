import Foundation

/// Builds screens' view models from the app's repositories. Views get this instead of
/// individual repositories, so navigation code never constructs networking.
@MainActor
final class ScreenFactory {
    let courses: CourseRepository
    let concepts: ConceptRepository
    let curriculum: CurriculumRepository
    let review: ReviewRepository
    let progress: ProgressRepository
    let documents: DocumentRepository
    let drafts: AnswerDraftStore

    init(
        courses: CourseRepository,
        concepts: ConceptRepository,
        curriculum: CurriculumRepository,
        review: ReviewRepository,
        progress: ProgressRepository,
        documents: DocumentRepository,
        drafts: AnswerDraftStore
    ) {
        self.courses = courses
        self.concepts = concepts
        self.curriculum = curriculum
        self.review = review
        self.progress = progress
        self.documents = documents
        self.drafts = drafts
    }

    func dashboard(for course: Course) -> CourseDashboardViewModel {
        CourseDashboardViewModel(course: course, courses: courses, progress: progress)
    }

    func chapter(_ route: ChapterRoute) -> ChapterViewModel {
        ChapterViewModel(
            route: route, courses: courses, progress: progress, curriculum: curriculum
        )
    }

    func topic(_ route: TopicRoute) -> TopicViewModel {
        TopicViewModel(route: route, courses: courses, progress: progress)
    }

    func concept(_ route: ConceptRoute) -> ConceptViewModel {
        ConceptViewModel(route: route, concepts: concepts, progress: progress)
    }

    func proposal(_ route: ProposalRoute) -> ProposalReviewViewModel {
        ProposalReviewViewModel(route: route, repository: curriculum)
    }

    func material(_ route: MaterialRoute) -> CourseDetailViewModel {
        CourseDetailViewModel(course: route.course, chapterId: route.chapterId, repository: documents)
    }

    func passages(for document: CourseDocument) -> SourcePassagesViewModel {
        SourcePassagesViewModel(document: document, repository: documents)
    }

    func session(_ launch: StudyLaunch) -> StudySessionViewModel {
        StudySessionViewModel(
            courseId: launch.courseId,
            courseTitle: launch.courseTitle,
            request: launch.request,
            repository: review,
            drafts: drafts
        )
    }

    func source(_ reference: SourceReference) -> SourceViewModel {
        SourceViewModel(reference: reference, repository: documents)
    }
}

/// A request to open a study session, presented full screen.
struct StudyLaunch: Identifiable, Equatable {
    let id = UUID()
    let courseId: UUID
    let courseTitle: String
    let request: SessionRequest
}

// Navigation values inside a Course (pushed on the Courses tab's stack).

struct ChapterRoute: Hashable {
    let course: Course
    let chapterId: UUID
    let title: String
}

struct TopicRoute: Hashable {
    let course: Course
    let topicId: UUID
    let title: String
}

struct ConceptRoute: Hashable {
    let course: Course
    let conceptId: UUID
    let title: String
}

struct ProposalRoute: Hashable {
    let course: Course
    let proposalId: UUID
}

/// A Course's study material, or one Chapter's.
struct MaterialRoute: Hashable {
    let course: Course
    let chapterId: UUID?
}
