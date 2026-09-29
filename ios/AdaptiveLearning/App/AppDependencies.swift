import Foundation

/// Composition root: the one place concrete implementations are chosen. Everything below the
/// App layer sees only protocols, so tests swap in fakes.
@MainActor
final class AppDependencies {
    let authSession: AuthSession
    let factory: ScreenFactory

    init(authSession: AuthSession, factory: ScreenFactory) {
        self.authSession = authSession
        self.factory = factory
    }

    static func live() -> AppDependencies {
        let tokenStore = KeychainTokenStore()
        let apiClient = APIClient(tokenStore: tokenStore)
        let authRepository = RemoteAuthRepository(apiClient: apiClient, tokenStore: tokenStore)
        return AppDependencies(
            authSession: AuthSession(repository: authRepository, tokenStore: tokenStore),
            factory: ScreenFactory(
                courses: RemoteCourseRepository(apiClient: apiClient),
                concepts: RemoteConceptRepository(apiClient: apiClient),
                curriculum: RemoteCurriculumRepository(apiClient: apiClient),
                review: RemoteReviewRepository(apiClient: apiClient),
                progress: RemoteProgressRepository(apiClient: apiClient),
                documents: RemoteDocumentRepository(apiClient: apiClient),
                drafts: UserDefaultsAnswerDraftStore()
            )
        )
    }
}
