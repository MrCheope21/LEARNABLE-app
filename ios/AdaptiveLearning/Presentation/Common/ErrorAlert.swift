import SwiftUI

extension View {
    /// Shows `message` in an alert while it's non-nil; dismissing clears it. Every screen routes
    /// its failures through this, so no error is silently swallowed.
    func errorAlert(_ message: Binding<String?>) -> some View {
        alert(
            "Something went wrong",
            isPresented: Binding(
                get: { message.wrappedValue != nil },
                set: { isPresented in
                    if !isPresented { message.wrappedValue = nil }
                }
            ),
            actions: { Button("OK", role: .cancel) {} },
            message: { Text(verbatim: message.wrappedValue ?? "") }
        )
    }
}
