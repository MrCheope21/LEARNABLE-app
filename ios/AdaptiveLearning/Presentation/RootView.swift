import SwiftUI

/// Switches between sign-in and the main app. Signing out tears down MainTabView and every view
/// model in it, so nothing from one account's Courses survives into the next session.
struct RootView: View {
    let dependencies: AppDependencies
    @State private var signInViewModel: SignInViewModel

    init(dependencies: AppDependencies) {
        self.dependencies = dependencies
        _signInViewModel = State(
            initialValue: SignInViewModel(session: dependencies.authSession)
        )
    }

    var body: some View {
        if dependencies.authSession.isSignedIn {
            MainTabView(dependencies: dependencies)
        } else {
            SignInView(viewModel: signInViewModel)
        }
    }
}
