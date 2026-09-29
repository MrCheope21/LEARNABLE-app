import SwiftUI
import UIKit

struct SettingsView: View {
    let viewModel: SettingsViewModel
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    // The app follows iOS's per-app language setting rather than keeping its own,
                    // so every screen and system control agrees on one language.
                    Button("Change App Language") {
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            openURL(url)
                        }
                    }
                } footer: {
                    Text("The app follows your device language. You can choose Italian or English for this app in the Settings app.")
                }

                Section {
                    Button("Sign Out", role: .destructive) {
                        viewModel.signOut()
                    }
                }
            }
            .navigationTitle("Settings")
        }
    }
}
