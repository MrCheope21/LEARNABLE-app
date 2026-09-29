import Foundation
import Observation

@MainActor
@Observable
final class CoursesViewModel {
    /// Course languages offered at creation; AI prompts will use the Course's language
    /// (docs/PROJECT_SPEC.md §69).
    static let supportedLanguages = ["it", "en"]
    static let defaultLanguage = Locale.current.language.languageCode?.identifier == "en"
        ? "en" : "it"

    private(set) var courses: [Course] = []
    private(set) var hasLoaded = false
    private(set) var isLoading = false
    private(set) var isCreating = false
    var isShowingNewCourse = false
    var errorMessage: String?
    var createErrorMessage: String?

    private let repository: CourseRepository

    init(repository: CourseRepository) {
        self.repository = repository
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            courses = try await repository.fetchCourses()
            hasLoaded = true
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Returns true when the Course was created, so the sheet knows to dismiss.
    func createCourse(title: String, language: String) async -> Bool {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return false }
        isCreating = true
        defer { isCreating = false }
        do {
            let course = try await repository.createCourse(
                CourseDraft(title: title, description: "", language: language)
            )
            courses.append(course)
            return true
        } catch is CancellationError {
            return false
        } catch {
            createErrorMessage = error.localizedDescription
            return false
        }
    }
}
