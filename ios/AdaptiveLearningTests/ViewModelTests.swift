import XCTest
import Security
@testable import AdaptiveLearning

@MainActor
final class CoursesViewModelTests: XCTestCase {
    func testLoadShowsCourses() async {
        let repository = FakeCourseRepository()
        repository.fetchResult = .success([.sample(title: "Diritto Commerciale")])
        let viewModel = CoursesViewModel(repository: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.courses.map(\.title), ["Diritto Commerciale"])
        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testLoadFailureIsShownNotSwallowed() async {
        let repository = FakeCourseRepository()
        repository.fetchResult = .failure(APIError.transport)
        let viewModel = CoursesViewModel(repository: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.errorMessage, APIError.transport.localizedDescription)
        XCTAssertFalse(viewModel.hasLoaded)
    }

    func testCreateCourseTrimsTitleAndAppends() async {
        let repository = FakeCourseRepository()
        let viewModel = CoursesViewModel(repository: repository)

        let created = await viewModel.createCourse(title: "  Banking  ", language: "en")

        XCTAssertTrue(created)
        XCTAssertEqual(
            repository.createdDrafts,
            [CourseDraft(title: "Banking", description: "", language: "en")]
        )
        XCTAssertEqual(viewModel.courses.map(\.title), ["Banking"])
    }

    func testBlankTitleIsNeverSent() async {
        let repository = FakeCourseRepository()
        let viewModel = CoursesViewModel(repository: repository)

        let created = await viewModel.createCourse(title: "   ", language: "it")

        XCTAssertFalse(created)
        XCTAssertTrue(repository.createdDrafts.isEmpty)
    }

    func testCreateFailureIsShownInTheSheet() async {
        let repository = FakeCourseRepository()
        repository.createError = APIError.transport
        let viewModel = CoursesViewModel(repository: repository)

        let created = await viewModel.createCourse(title: "Banking", language: "en")

        XCTAssertFalse(created)
        XCTAssertNotNil(viewModel.createErrorMessage)
        XCTAssertTrue(viewModel.courses.isEmpty)
    }
}

@MainActor
final class HomeViewModelTests: XCTestCase {
    func testLoadShowsTheBackendsSummary() async throws {
        let repository = FakeProgressRepository()
        repository.home = .success(try Fixtures.decode(HomeSummary.self, Fixtures.home))
        let viewModel = HomeViewModel(progress: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.state.value?.courses.map(\.title), ["Diritto bancario"])
        XCTAssertEqual(viewModel.state.value?.totals.laterToday, 1)
    }

    func testFirstLoadFailureShowsRetryableError() async {
        let repository = FakeProgressRepository()
        repository.home = .failure(APIError.transport)
        let viewModel = HomeViewModel(progress: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.state, .failed(APIError.transport.localizedDescription))
    }

    func testRefreshFailureKeepsTheLastSummary() async throws {
        let repository = FakeProgressRepository()
        repository.home = .success(try Fixtures.decode(HomeSummary.self, Fixtures.home))
        let viewModel = HomeViewModel(progress: repository)
        await viewModel.load()

        repository.home = .failure(APIError.transport)
        await viewModel.load()

        XCTAssertNotNil(viewModel.state.value)
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testPrimaryActionsPickTheCourseWithTheMostWork() async {
        let busy = summary("Busy", due: 5, new: 0)
        let quiet = summary("Quiet", due: 1, new: 3)
        let repository = FakeProgressRepository()
        repository.home = .success(HomeSummary(totals: .empty, courses: [quiet, busy]))
        let viewModel = HomeViewModel(progress: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.reviewLaunch?.courseTitle, "Busy")
        XCTAssertEqual(viewModel.reviewLaunch?.request, .scheduledReview)
        XCTAssertEqual(viewModel.learnLaunch?.courseTitle, "Quiet")
        XCTAssertEqual(viewModel.learnLaunch?.request.intent, .learn)
    }

    func testNothingDueOffersNoReviewButton() async {
        let repository = FakeProgressRepository()
        repository.home = .success(HomeSummary(totals: .empty, courses: [summary("A", due: 0, new: 0)]))
        let viewModel = HomeViewModel(progress: repository)

        await viewModel.load()

        XCTAssertNil(viewModel.reviewLaunch)
        XCTAssertNil(viewModel.learnLaunch)
    }

    private func summary(_ title: String, due: Int, new: Int) -> CourseSummary {
        var load = ReviewLoad.empty
        load.dueNow = due
        load.newToLearn = new
        return CourseSummary(
            courseId: UUID(), title: title, reviewLoad: load,
            activeConcepts: 1, mastery: nil, weakConcepts: []
        )
    }
}

@MainActor
final class ProgressDashboardViewModelTests: XCTestCase {
    func testLoadsTheFirstCoursesProgress() async throws {
        let repository = FakeProgressRepository()
        let home = try Fixtures.decode(HomeSummary.self, Fixtures.home)
        repository.home = .success(home)
        repository.progress = .success(try Fixtures.decode(CourseProgress.self, Fixtures.progress))
        let viewModel = ProgressDashboardViewModel(repository: repository)

        await viewModel.load()

        XCTAssertEqual(viewModel.selectedCourseId, home.courses.first?.courseId)
        XCTAssertEqual(repository.progressRequests, [home.courses[0].courseId])
        // Curriculum and memory stay separate numbers.
        XCTAssertEqual(viewModel.progress.value?.curriculum.active, 1)
        XCTAssertEqual(viewModel.progress.value?.memory.mastery, 0.125)
    }

    func testProgressFailureIsRetryable() async throws {
        let repository = FakeProgressRepository()
        repository.home = .success(try Fixtures.decode(HomeSummary.self, Fixtures.home))
        repository.progress = .failure(APIError.transport)
        let viewModel = ProgressDashboardViewModel(repository: repository)

        await viewModel.load()
        XCTAssertEqual(viewModel.progress, .failed(APIError.transport.localizedDescription))

        repository.progress = .success(try Fixtures.decode(CourseProgress.self, Fixtures.progress))
        await viewModel.loadProgress()
        XCTAssertNotNil(viewModel.progress.value)
    }
}

@MainActor
final class SignInViewModelTests: XCTestCase {
    private func makeViewModel(
        error: Error? = nil
    ) -> (SignInViewModel, AuthSession, FakeAuthRepository) {
        let repository = FakeAuthRepository()
        repository.error = error
        let session = AuthSession(
            repository: repository,
            tokenStore: InMemoryTokenStore(),
            notificationCenter: NotificationCenter()
        )
        return (SignInViewModel(session: session), session, repository)
    }

    func testSuccessfulSignInSignsInAndClearsPassword() async {
        let (viewModel, session, _) = makeViewModel()
        viewModel.email = "student@example.com"
        viewModel.password = "correct-horse-battery"

        await viewModel.submit()

        XCTAssertTrue(session.isSignedIn)
        XCTAssertEqual(viewModel.password, "")
        XCTAssertNil(viewModel.errorMessage)
    }

    func testShortPasswordOnRegisterIsRejectedWithoutARequest() async {
        let (viewModel, session, repository) = makeViewModel()
        viewModel.mode = .register
        viewModel.email = "student@example.com"
        viewModel.password = "short"

        await viewModel.submit()

        XCTAssertEqual(repository.registerCalls, 0)
        XCTAssertFalse(session.isSignedIn)
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testWrongCredentialsShowAFriendlyMessage() async {
        let (viewModel, session, _) = makeViewModel(error: APIError.unauthorized(
            errorType: "authentication_failed", message: "Incorrect email or password"
        ))
        viewModel.email = "student@example.com"
        viewModel.password = "wrong-password"

        await viewModel.submit()

        XCTAssertFalse(session.isSignedIn)
        XCTAssertEqual(viewModel.errorMessage, String(localized: "Incorrect email or password."))
    }

    func testTakenEmailShowsAFriendlyMessage() async {
        let (viewModel, _, _) = makeViewModel(error: APIError.server(
            status: 409, errorType: "conflict", message: "Email already registered"
        ))
        viewModel.mode = .register
        viewModel.email = "taken@example.com"
        viewModel.password = "a-long-enough-password"

        await viewModel.submit()

        XCTAssertEqual(
            viewModel.errorMessage, String(localized: "An account with this email already exists.")
        )
    }
}

@MainActor
final class AuthSessionTests: XCTestCase {
    func testStartsSignedInWhenATokenIsStored() {
        let session = AuthSession(
            repository: FakeAuthRepository(),
            tokenStore: InMemoryTokenStore(token: "stored"),
            notificationCenter: NotificationCenter()
        )
        XCTAssertTrue(session.isSignedIn)
    }

    func testSessionExpiryNotificationSignsOut() async {
        let center = NotificationCenter()
        let session = AuthSession(
            repository: FakeAuthRepository(),
            tokenStore: InMemoryTokenStore(token: "stored"),
            notificationCenter: center
        )

        center.post(name: .apiSessionExpired, object: nil)

        let signedOut = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in !session.isSignedIn }, object: nil
        )
        await fulfillment(of: [signedOut], timeout: 2)
    }

    func testSignOutClearsTheSession() {
        let repository = FakeAuthRepository()
        let session = AuthSession(
            repository: repository,
            tokenStore: InMemoryTokenStore(token: "stored"),
            notificationCenter: NotificationCenter()
        )

        session.signOut()

        XCTAssertFalse(session.isSignedIn)
        XCTAssertEqual(repository.signOutCalls, 1)
    }
}

final class KeychainErrorTests: XCTestCase {
    func testUsersNeverSeeTheRawKeychainStatus() {
        // A failed token save once surfaced as "(AdaptiveLearning.KeychainError error 1.)".
        let message = KeychainError(status: errSecMissingEntitlement).localizedDescription
        XCTAssertEqual(
            message, String(localized: "Couldn't save your sign-in on this device. Please try again.")
        )
    }
}
