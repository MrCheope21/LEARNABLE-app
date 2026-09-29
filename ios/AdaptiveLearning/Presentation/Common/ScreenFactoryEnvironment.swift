import SwiftUI

private struct ScreenFactoryKey: EnvironmentKey {
    static let defaultValue: ScreenFactory? = nil
}

extension EnvironmentValues {
    /// Set once in MainTabView, so deeply nested screens can build the next screen's view model
    /// without passing the factory through every initializer.
    var screenFactory: ScreenFactory? {
        get { self[ScreenFactoryKey.self] }
        set { self[ScreenFactoryKey.self] = newValue }
    }
}
