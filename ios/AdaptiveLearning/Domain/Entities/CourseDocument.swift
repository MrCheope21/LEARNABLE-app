import Foundation

/// A file in a Course's Knowledge Repository (docs/PROJECT_SPEC.md §16). Named CourseDocument to
/// stay clear of the many "Document" types in Apple's frameworks.
struct CourseDocument: Identifiable, Codable, Equatable, Hashable {
    let id: UUID
    let courseId: UUID
    var filename: String
    var kind: DocumentKind
    var sizeBytes: Int
    var status: DocumentStatus
    /// Why processing failed; shown to the user as-is.
    var errorMessage: String?
    var pageCount: Int?
    var chunkCount: Int
    var createdAt: Date
}

/// docs/API.md: upload returns PROCESSING; the backend moves it to READY or FAILED.
enum DocumentStatus: String, Codable, Hashable {
    case processing = "PROCESSING"
    case ready = "READY"
    case failed = "FAILED"
}

enum DocumentKind: String, Codable, Hashable {
    case pdf = "PDF"
    case text = "TEXT"
    case markdown = "MARKDOWN"
    case docx = "DOCX"
    case pptx = "PPTX"
    case image = "IMAGE"
    /// A kind added to the backend after this app version shipped. Display-only, so it must not
    /// make the whole document list fail to decode.
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = DocumentKind(rawValue: raw) ?? .unknown
    }
}

/// One passage of a document, with where it came from — "View source" (docs/PROJECT_SPEC.md §66).
struct SourcePassage: Identifiable, Codable, Equatable {
    let id: UUID
    let documentId: UUID
    var position: Int
    /// PDF page or PowerPoint slide number.
    var pageNumber: Int?
    /// Nearest heading, PDF bookmark or slide title.
    var section: String?
    var text: String
}
