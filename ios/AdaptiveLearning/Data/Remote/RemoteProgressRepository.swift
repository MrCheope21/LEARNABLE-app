import Foundation

/// Progress, review load and Home (docs/API.md "Progress and review load"). The device's UTC
/// offset is sent so "today" and "tomorrow" are the user's calendar days.
struct RemoteProgressRepository: ProgressRepository {
    let apiClient: APIClient
    var timeZone: TimeZone = .current

    private var offset: [URLQueryItem] {
        [URLQueryItem(name: "utc_offset_minutes", value: String(timeZone.secondsFromGMT() / 60))]
    }

    func fetchHome() async throws -> HomeSummary {
        try await apiClient.get("/api/v1/home", query: offset)
    }

    func fetchProgress(courseId: UUID) async throws -> CourseProgress {
        try await apiClient.get("/api/v1/courses/\(courseId.uuidString)/progress", query: offset)
    }

    func fetchReviewLoad(courseId: UUID) async throws -> ReviewLoad {
        try await apiClient.get(
            "/api/v1/courses/\(courseId.uuidString)/review-load", query: offset
        )
    }
}
