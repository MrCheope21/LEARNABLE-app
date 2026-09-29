import Foundation
import Observation

@MainActor
@Observable
final class SettingsViewModel {
    private let session: AuthSession

    init(session: AuthSession) {
        self.session = session
    }

    func signOut() {
        session.signOut()
    }
}
