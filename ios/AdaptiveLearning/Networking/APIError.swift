import Foundation

/// Every way a backend call can fail. Keeps the HTTP status and the backend's error envelope
/// (`error_type`, `message` — docs/API.md) so callers can tell a 401 from a 404 from a 409.
enum APIError: Error, Equatable {
    /// Server unreachable, timed out, or the device is offline.
    case transport
    case unauthorized(errorType: String, message: String)
    case server(status: Int, errorType: String, message: String)
    case invalidResponse
}

extension APIError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .transport:
            return String(localized: "Can't reach the server. Check your connection and try again.")
        case .unauthorized:
            return String(localized: "Your session has expired. Please sign in again.")
        case .server(_, let errorType, let message):
            switch errorType {
            case "validation_error":
                return String(localized: "Some of the information entered isn't valid.")
            case "not_found":
                return String(localized: "This item no longer exists.")
            case "internal_error":
                return String(localized: "Something went wrong on the server. Please try again.")
            case "payload_too_large":
                return String(localized: "This file is too large (max 50 MB).")
            case "unsupported_media_type":
                return String(
                    localized: "This file type isn't supported. Use PDF, Word, PowerPoint, text or Markdown files."
                )
            case "ai_not_configured":
                return String(localized: "The AI isn't set up on the server yet.")
            case "ai_unavailable":
                return String(localized: "The AI is temporarily unavailable. Please try again later.")
            case "ai_invalid_output":
                return String(localized: "The AI gave an unusable response. Please try again.")
            case "invalid_state_transition":
                return String(localized: "That action isn't possible in the current state.")
            default:
                // Backend messages are English-only; known error types above are localized.
                return message
            }
        case .invalidResponse:
            return String(localized: "The server sent an unexpected response.")
        }
    }
}
