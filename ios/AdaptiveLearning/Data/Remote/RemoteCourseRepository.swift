import Foundation

/// Courses and their hierarchy (docs/API.md "Curriculum"). The backend only ever returns the
/// signed-in user's data, so there's no client-side filtering to get wrong.
struct RemoteCourseRepository: CourseRepository {
    let apiClient: APIClient

    func fetchCourses() async throws -> [Course] {
        try await apiClient.get("/api/v1/courses")
    }

    func createCourse(_ draft: CourseDraft) async throws -> Course {
        try await apiClient.post("/api/v1/courses", body: draft)
    }

    func fetchOutline(courseId: UUID) async throws -> [ChapterNode] {
        try await apiClient.get("/api/v1/courses/\(courseId.uuidString)/outline")
    }

    func createChapter(courseId: UUID, title: String) async throws {
        let _: CreatedResource = try await apiClient.post(
            "/api/v1/courses/\(courseId.uuidString)/chapters", body: TitleBody(title: title)
        )
    }
}

private struct TitleBody: Encodable {
    let title: String
}

/// Only the id of something just created; the caller reloads the tree.
struct CreatedResource: Decodable {
    let id: UUID
}
