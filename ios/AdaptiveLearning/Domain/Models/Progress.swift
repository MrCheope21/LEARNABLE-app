import Foundation

// Progress, review load and the Home summary (docs/API.md "Progress and review load"). Every
// number here is computed by the backend; the app displays them and never recalculates
// schedules itself.

/// Upcoming reviews by the user's calendar day. Buckets don't overlap.
struct ReviewLoad: Codable, Equatable {
    var dueNow: Int
    /// The part of `dueNow` that was due before today.
    var overdue: Int
    var laterToday: Int
    var tomorrow: Int
    var next7Days: Int
    var later: Int
    var newToLearn: Int

    static let empty = ReviewLoad(
        dueNow: 0, overdue: 0, laterToday: 0, tomorrow: 0, next7Days: 0, later: 0, newToLearn: 0
    )

    /// Everything due by the end of today.
    var today: Int { dueNow + laterToday }
}

/// How far through the material (study states). Says nothing about memory.
struct CurriculumProgress: Codable, Equatable {
    var concepts: Int
    var notStudied: Int
    var studied: Int
    var active: Int
    var paused: Int
    var completed: Int
}

/// How well the trained material is retained. `mastery` is an estimate, not a measurement.
struct MemoryProgress: Codable, Equatable {
    var itemsTrained: Int
    var new: Int
    var learning: Int
    var review: Int
    var relearning: Int
    var mastered: Int
    var markedHard: Int
    var mastery: Double?
}

struct ConceptProgress: Codable, Equatable, Identifiable {
    let id: UUID
    var title: String
    var studyState: StudyState
    var memory: MemoryProgress
    var misconceptions: [String]
}

struct TopicProgress: Codable, Equatable, Identifiable {
    let id: UUID
    var title: String
    var curriculum: CurriculumProgress
    var memory: MemoryProgress
    var concepts: [ConceptProgress]
}

struct ChapterProgress: Codable, Equatable, Identifiable {
    let id: UUID
    var title: String
    var curriculum: CurriculumProgress
    var memory: MemoryProgress
    var topics: [TopicProgress]
}

struct CourseProgress: Codable, Equatable {
    let courseId: UUID
    var curriculum: CurriculumProgress
    var memory: MemoryProgress
    var reviewLoad: ReviewLoad
    var chapters: [ChapterProgress]

    func chapter(_ id: UUID) -> ChapterProgress? {
        chapters.first { $0.id == id }
    }

    func topic(_ id: UUID) -> TopicProgress? {
        chapters.flatMap(\.topics).first { $0.id == id }
    }

    func concept(_ id: UUID) -> ConceptProgress? {
        chapters.flatMap(\.topics).flatMap(\.concepts).first { $0.id == id }
    }
}

struct WeakConcept: Codable, Equatable, Identifiable {
    let id: UUID
    var title: String
    var lapses: Int
    var markedHard: Int
}

struct CourseSummary: Codable, Equatable, Identifiable {
    let courseId: UUID
    var title: String
    var reviewLoad: ReviewLoad
    var activeConcepts: Int
    var mastery: Double?
    var weakConcepts: [WeakConcept]

    var id: UUID { courseId }
}

/// `GET /api/v1/home`: the user's day, per Course.
struct HomeSummary: Codable, Equatable {
    var totals: ReviewLoad
    var courses: [CourseSummary]

    static let empty = HomeSummary(totals: .empty, courses: [])
}
