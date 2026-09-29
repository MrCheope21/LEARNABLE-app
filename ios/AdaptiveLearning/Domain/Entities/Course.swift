import Foundation

/// Highest-level user-owned learning environment (docs/PROJECT_SPEC.md §9). Isolated from every
/// other Course — nothing in this app may merge data across Course boundaries (§10).
struct Course: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    var title: String
    var description: String
    var language: String
}
