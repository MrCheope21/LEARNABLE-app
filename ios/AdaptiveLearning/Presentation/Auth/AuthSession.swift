import Foundation
import Observation

/// App-wide signed-in state. Signed in iff a token is stored. When any authenticated request
/// gets a 401, APIClient deletes the token and posts `.apiSessionExpired`, which signs out here.
@MainActor
@Observable
final class AuthSession {
    private(set) var isSignedIn: Bool

    private let repository: AuthRepository

    init(
        repository: AuthRepository,
        tokenStore: TokenStore,
        notificationCenter: NotificationCenter = .default
    ) {
        self.repository = repository
        isSignedIn = tokenStore.load() != nil
        // Posted from whatever thread the request finished on, hence queue: .main.
        notificationCenter.addObserver(
            forName: .apiSessionExpired, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.isSignedIn = false
            }
        }
    }

    func signIn(email: String, password: String) async throws {
        try await repository.signIn(email: email, password: password)
        isSignedIn = true
    }

    func register(email: String, password: String) async throws {
        try await repository.register(email: email, password: password)
        isSignedIn = true
    }

    func signOut() {
        repository.signOut()
        isSignedIn = false
    }
}
