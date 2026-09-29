import Foundation

/// Where the API access token lives between launches. The app uses KeychainTokenStore
/// (Persistence/); tests use InMemoryTokenStore.
protocol TokenStore: AnyObject {
    func load() -> String?
    func save(_ token: String) throws
    func delete()
}

final class InMemoryTokenStore: TokenStore {
    private var token: String?

    init(token: String? = nil) {
        self.token = token
    }

    func load() -> String? { token }
    func save(_ token: String) throws { self.token = token }
    func delete() { token = nil }
}
