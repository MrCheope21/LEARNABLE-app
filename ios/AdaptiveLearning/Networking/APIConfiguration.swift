import Foundation

/// Base URL for the backend (see docs/API.md). Points at local dev by default; release builds
/// override this via build configuration once release infrastructure exists.
enum APIConfiguration {
    static let baseURL = URL(string: "http://localhost:8000")!
}
