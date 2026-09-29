import Foundation
import Security

/// Keeps the access token in the Keychain — never UserDefaults (docs/PROJECT_SPEC.md §70:
/// secure credential storage). Readable after first unlock, never synced to other devices or
/// included in backups.
final class KeychainTokenStore: TokenStore {
    private let service: String
    private let account = "accessToken"

    init(service: String = Bundle.main.bundleIdentifier ?? "com.adaptivelearning.app") {
        self.service = service
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    func load() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    func save(_ token: String) throws {
        delete()
        var query = baseQuery
        query[kSecValueData as String] = Data(token.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainError(status: status)
        }
    }

    func delete() {
        _ = SecItemDelete(baseQuery as CFDictionary)
    }
}

struct KeychainError: Error, LocalizedError {
    let status: OSStatus

    // The OSStatus is for logs, not for users.
    var errorDescription: String? {
        String(localized: "Couldn't save your sign-in on this device. Please try again.")
    }
}
