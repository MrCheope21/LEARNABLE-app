import Foundation
import Observation

@MainActor
@Observable
final class SignInViewModel {
    enum Mode {
        case signIn
        case register
    }

    /// Mirrors the backend's registration policy (docs/API.md), checked here first so the user
    /// gets immediate feedback instead of a round trip.
    static let minimumPasswordLength = 12

    var mode: Mode = .signIn
    var email = ""
    var password = ""
    private(set) var isSubmitting = false
    var errorMessage: String?

    private let session: AuthSession

    init(session: AuthSession) {
        self.session = session
    }

    var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !password.isEmpty
            && !isSubmitting
    }

    func toggleMode() {
        mode = mode == .signIn ? .register : .signIn
        errorMessage = nil
    }

    func submit() async {
        if mode == .register && password.count < Self.minimumPasswordLength {
            errorMessage = String(localized: "Use at least 12 characters for your password.")
            return
        }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            switch mode {
            case .signIn:
                try await session.signIn(email: email, password: password)
            case .register:
                try await session.register(email: email, password: password)
            }
            password = ""
        } catch is CancellationError {
            return
        } catch APIError.unauthorized {
            errorMessage = String(localized: "Incorrect email or password.")
        } catch APIError.server(_, "conflict", _) {
            errorMessage = String(localized: "An account with this email already exists.")
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
