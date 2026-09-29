import SwiftUI

/// Main navigation: Home, Courses, Review, Progress, Settings (docs/PROJECT_SPEC.md §63).
/// View models are created once here and live as long as the signed-in session.
struct MainTabView: View {
    let factory: ScreenFactory
    @State private var home: HomeViewModel
    @State private var courses: CoursesViewModel
    @State private var review: HomeViewModel
    @State private var progress: ProgressDashboardViewModel
    @State private var settings: SettingsViewModel

    init(dependencies: AppDependencies) {
        let factory = dependencies.factory
        self.factory = factory
        _home = State(initialValue: HomeViewModel(progress: factory.progress))
        _courses = State(initialValue: CoursesViewModel(repository: factory.courses))
        _review = State(initialValue: HomeViewModel(progress: factory.progress))
        _progress = State(initialValue: ProgressDashboardViewModel(repository: factory.progress))
        _settings = State(initialValue: SettingsViewModel(session: dependencies.authSession))
    }

    var body: some View {
        TabView {
            HomeView(viewModel: home, factory: factory)
                .tabItem { Label("Home", systemImage: "house") }
            CoursesView(viewModel: courses, factory: factory)
                .tabItem { Label("Courses", systemImage: "books.vertical") }
            ReviewHubView(viewModel: review, factory: factory)
                .tabItem { Label("Review", systemImage: "checkmark.circle") }
            ProgressDashboardView(viewModel: progress)
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
            SettingsView(viewModel: settings)
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .environment(\.screenFactory, factory)
    }
}
