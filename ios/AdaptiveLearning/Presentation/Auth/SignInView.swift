import SwiftUI

struct SignInView: View {
    @Bindable var viewModel: SignInViewModel

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Email", text: $viewModel.email)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $viewModel.password)
                        .textContentType(viewModel.mode == .register ? .newPassword : .password)
                } footer: {
                    if viewModel.mode == .register {
                        Text("At least 12 characters.")
                    }
                }

                Section {
                    Button {
                        Task { await viewModel.submit() }
                    } label: {
                        HStack {
                            Text(submitTitle)
                            if viewModel.isSubmitting {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(!viewModel.canSubmit)
                }

                Section {
                    Button(switchModeTitle) { viewModel.toggleMode() }
                }
            }
            .navigationTitle(submitTitle)
            .errorAlert($viewModel.errorMessage)
        }
    }

    // Typed as LocalizedStringKey so these are looked up in the string catalog; a bare ternary of
    // string literals would be inferred as String and shown untranslated.
    private var submitTitle: LocalizedStringKey {
        viewModel.mode == .signIn ? "Sign In" : "Create Account"
    }

    private var switchModeTitle: LocalizedStringKey {
        viewModel.mode == .signIn ? "Create an account" : "I already have an account"
    }
}
