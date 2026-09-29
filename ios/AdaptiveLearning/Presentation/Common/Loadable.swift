import SwiftUI

/// The state of a screen backed by the network. Every such screen shows loading, content, or an
/// error with a retry — never an endless spinner.
enum Loadable<Value> {
    case loading
    case loaded(Value)
    case failed(String)

    var value: Value? {
        if case .loaded(let value) = self { return value }
        return nil
    }
}

extension Loadable: Equatable where Value: Equatable {}

/// A message safe to show an ordinary user: the app's own localized text for known errors,
/// never a raw technical payload.
func userMessage(for error: Error) -> String {
    if let localized = error as? LocalizedError, let description = localized.errorDescription {
        return description
    }
    return String(localized: "Something went wrong. Please try again.")
}

/// Renders a Loadable: a spinner, the content, or an error with "Try Again".
struct LoadableView<Value, Content: View>: View {
    let state: Loadable<Value>
    let retry: () async -> Void
    @ViewBuilder let content: (Value) -> Content

    var body: some View {
        switch state {
        case .loading:
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let message):
            ContentUnavailableView {
                Label("Couldn't Load", systemImage: "exclamationmark.triangle")
            } description: {
                Text(verbatim: message)
            } actions: {
                Button("Try Again") {
                    Task { await retry() }
                }
                .buttonStyle(.borderedProminent)
            }
        case .loaded(let value):
            content(value)
        }
    }
}
