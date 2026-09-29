import Foundation

extension Notification.Name {
    /// Posted when an authenticated request gets a 401: the stored token was expired or revoked
    /// and has been deleted. AuthSession listens and returns the app to sign-in.
    static let apiSessionExpired = Notification.Name("apiSessionExpired")
}

/// Thin JSON HTTP client. The iOS app talks ONLY to this backend — never directly to an AI
/// provider (docs/PROJECT_SPEC.md §32; docs/ARCHITECTURE.md §2).
struct APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let tokenStore: TokenStore
    private let notificationCenter: NotificationCenter

    init(
        baseURL: URL = APIConfiguration.baseURL,
        session: URLSession = .shared,
        tokenStore: TokenStore,
        notificationCenter: NotificationCenter = .default
    ) {
        self.baseURL = baseURL
        self.session = session
        self.tokenStore = tokenStore
        self.notificationCenter = notificationCenter
    }

    func get<Response: Decodable>(
        _ path: String,
        query: [URLQueryItem] = []
    ) async throws -> Response {
        var url = baseURL.appending(path: path)
        if !query.isEmpty {
            url.append(queryItems: query)
        }
        return try await send(URLRequest(url: url))
    }

    func post<Body: Encodable, Response: Decodable>(
        _ path: String,
        body: Body
    ) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder.apiEncoder.encode(body)
        return try await send(request)
    }

    /// For action endpoints that take no body (e.g. `POST /concepts/{id}/activate`).
    func post<Response: Decodable>(_ path: String) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        return try await send(request)
    }

    func patch<Body: Encodable, Response: Decodable>(
        _ path: String,
        body: Body
    ) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder.apiEncoder.encode(body)
        return try await send(request)
    }

    /// Multipart upload of one file in the form field "file" (docs/API.md documents), plus any
    /// plain form fields (e.g. `chapter_id`).
    func upload<Response: Decodable>(
        _ path: String,
        fileName: String,
        data: Data,
        fields: [String: String] = [:]
    ) async throws -> Response {
        let boundary = "LearnableBoundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        // Large study PDFs on a slow connection outlast the 60-second default.
        request.timeoutInterval = 300
        request.setValue(
            "multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type"
        )
        request.httpBody = Self.multipartBody(
            boundary: boundary, fileName: fileName, data: data, fields: fields
        )
        return try await send(request)
    }

    /// For endpoints that answer 204 No Content.
    func delete(_ path: String) async throws {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "DELETE"
        _ = try await perform(request)
    }

    static func multipartBody(
        boundary: String,
        fileName: String,
        data: Data,
        fields: [String: String] = [:]
    ) -> Data {
        // Quotes or line breaks in a filename would break out of the Content-Disposition header.
        let safeName = fileName
            .replacingOccurrences(of: "\"", with: "'")
            .components(separatedBy: .newlines)
            .joined()
        var body = Data()
        for (name, value) in fields.sorted(by: { $0.key < $1.key }) {
            body.append(Data("--\(boundary)\r\n".utf8))
            body.append(Data("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".utf8))
            body.append(Data("\(value)\r\n".utf8))
        }
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(
            Data("Content-Disposition: form-data; name=\"file\"; filename=\"\(safeName)\"\r\n".utf8)
        )
        // The backend identifies the type from the file's content, so no client-side guessing.
        body.append(Data("Content-Type: application/octet-stream\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return body
    }

    private func send<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let data = try await perform(request)
        do {
            return try JSONDecoder.apiDecoder.decode(Response.self, from: data)
        } catch {
            throw APIError.invalidResponse
        }
    }

    /// Transport, auth header, and error mapping; returns the body of a 2xx response.
    private func perform(_ request: URLRequest) async throws -> Data {
        var request = request
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let token = tokenStore.load()
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            // A cancelled request (view went away, pull-to-refresh restarted) isn't a failure the
            // user needs to hear about; callers ignore CancellationError.
            if Task.isCancelled || error is CancellationError
                || (error as? URLError)?.code == .cancelled {
                throw CancellationError()
            }
            throw APIError.transport
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200..<300).contains(http.statusCode) else {
            let envelope = try? JSONDecoder.apiDecoder.decode(ErrorEnvelope.self, from: data)
            let errorType = envelope?.errorType ?? "http_error"
            let message = envelope?.message
                ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            if http.statusCode == 401 {
                // Only an authenticated request can mean "session expired"; a 401 without a
                // token is simply wrong credentials at login.
                if token != nil {
                    tokenStore.delete()
                    notificationCenter.post(name: .apiSessionExpired, object: nil)
                }
                throw APIError.unauthorized(errorType: errorType, message: message)
            }
            throw APIError.server(status: http.statusCode, errorType: errorType, message: message)
        }

        return data
    }
}

private struct ErrorEnvelope: Decodable {
    let errorType: String
    let message: String
}

extension JSONDecoder {
    static let apiDecoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // Not `.iso8601`: that strategy rejects fractional seconds, and the backend always sends
        // them (docs/API.md timestamp contract: "2026-09-23T08:42:33.720Z").
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            guard let date = APIDateFormat.date(from: string) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Expected an ISO-8601 UTC timestamp, got \(string)"
                )
            }
            return date
        }
        return decoder
    }()
}

extension JSONEncoder {
    static let apiEncoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

enum APIDateFormat {
    private static let withFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let withoutFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func date(from string: String) -> Date? {
        withFractionalSeconds.date(from: string) ?? withoutFractionalSeconds.date(from: string)
    }
}
