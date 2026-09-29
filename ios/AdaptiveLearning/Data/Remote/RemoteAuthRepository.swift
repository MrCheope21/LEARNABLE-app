import Foundation

/// `POST /api/v1/auth/register` and `/login` (docs/API.md).
struct RemoteAuthRepository: AuthRepository {
    let apiClient: APIClient
    let tokenStore: TokenStore

    func signIn(email: String, password: String) async throws {
        // A stale token must not ride along on the login request.
        tokenStore.delete()
        let response: TokenResponse = try await apiClient.post(
            "/api/v1/auth/login",
            body: Credentials(email: email, password: password)
        )
        try tokenStore.save(response.accessToken)
    }

    func register(email: String, password: String) async throws {
        let _: RegisteredUser = try await apiClient.post(
            "/api/v1/auth/register",
            body: Credentials(email: email, password: password)
        )
        try await signIn(email: email, password: password)
    }

    func signOut() {
        tokenStore.delete()
    }
}

private struct Credentials: Encodable {
    let email: String
    let password: String
}

private struct TokenResponse: Decodable {
    let accessToken: String
}

private struct RegisteredUser: Decodable {
    let id: UUID
}
