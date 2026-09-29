import XCTest
@testable import AdaptiveLearning

/// Serves canned responses to URLSession so APIClient is tested without a network or backend.
final class StubURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class APIClientTests: XCTestCase {
    private var tokenStore: InMemoryTokenStore!
    private var notificationCenter: NotificationCenter!
    private var client: APIClient!

    override func setUp() {
        super.setUp()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        tokenStore = InMemoryTokenStore()
        notificationCenter = NotificationCenter()
        client = APIClient(
            baseURL: URL(string: "https://api.test")!,
            session: URLSession(configuration: configuration),
            tokenStore: tokenStore,
            notificationCenter: notificationCenter
        )
    }

    override func tearDown() {
        StubURLProtocol.handler = nil
        super.tearDown()
    }

    private func respond(
        status: Int,
        json: String,
        inspect: ((URLRequest) -> Void)? = nil
    ) {
        StubURLProtocol.handler = { request in
            inspect?(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }
    }

    func testSendsBearerTokenWhenSignedIn() async throws {
        try tokenStore.save("abc123")
        var seen: URLRequest?
        respond(status: 200, json: "[]") { seen = $0 }

        let _: [Course] = try await client.get("/api/v1/courses")

        XCTAssertEqual(seen?.value(forHTTPHeaderField: "Authorization"), "Bearer abc123")
        XCTAssertEqual(seen?.url?.host, "api.test")
        XCTAssertEqual(seen?.url?.path, "/api/v1/courses")
    }

    func testSendsNoAuthorizationHeaderWhenSignedOut() async throws {
        var seen: URLRequest?
        respond(status: 200, json: "[]") { seen = $0 }

        let _: [Course] = try await client.get("/api/v1/courses")

        XCTAssertNil(seen?.value(forHTTPHeaderField: "Authorization"))
    }

    func testQueryItemsArePercentEncodedNotMangled() async throws {
        var seen: URLRequest?
        respond(status: 200, json: "[]") { seen = $0 }

        let _: [Course] = try await client.get(
            "/api/v1/review/due", query: [URLQueryItem(name: "course_id", value: "a b")]
        )

        XCTAssertEqual(seen?.url?.path, "/api/v1/review/due")
        XCTAssertEqual(seen?.url?.query, "course_id=a%20b")
    }

    func testDecodesCoursesFromBackendShape() async throws {
        respond(status: 200, json: """
        [{"id": "3f2b8c4e-1d2a-4b5c-9e8f-7a6b5c4d3e2f", "title": "Macroeconomia",
          "description": "", "language": "it",
          "created_at": "2026-09-23T08:42:33.720Z", "updated_at": "2026-09-23T08:42:33.720Z"}]
        """)

        let courses: [Course] = try await client.get("/api/v1/courses")

        XCTAssertEqual(courses.map(\.title), ["Macroeconomia"])
    }

    func testErrorEnvelopeIsPreserved() async {
        respond(status: 409, json: """
        {"error_type": "conflict", "message": "Email already registered", "details": {}}
        """)

        do {
            let _: [Course] = try await client.get("/api/v1/courses")
            XCTFail("expected an error")
        } catch let error as APIError {
            XCTAssertEqual(
                error,
                .server(status: 409, errorType: "conflict", message: "Email already registered")
            )
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testUnauthorizedWithTokenClearsTokenAndSignalsSessionExpiry() async throws {
        try tokenStore.save("expired-token")
        let expiry = expectation(
            forNotification: .apiSessionExpired, object: nil, notificationCenter: notificationCenter
        )
        respond(status: 401, json: """
        {"error_type": "authentication_failed", "message": "Invalid or expired token", "details": {}}
        """)

        do {
            let _: [Course] = try await client.get("/api/v1/courses")
            XCTFail("expected an error")
        } catch APIError.unauthorized {
            // expected
        } catch {
            XCTFail("unexpected error \(error)")
        }

        await fulfillment(of: [expiry], timeout: 1)
        XCTAssertNil(tokenStore.load())
    }

    func testUnauthorizedWithoutTokenIsJustWrongCredentials() async {
        let expiry = expectation(
            forNotification: .apiSessionExpired, object: nil, notificationCenter: notificationCenter
        )
        expiry.isInverted = true
        respond(status: 401, json: """
        {"error_type": "authentication_failed", "message": "Incorrect email or password", "details": {}}
        """)

        do {
            let _: [Course] = try await client.get("/api/v1/auth/login")
            XCTFail("expected an error")
        } catch APIError.unauthorized {
            // expected
        } catch {
            XCTFail("unexpected error \(error)")
        }

        await fulfillment(of: [expiry], timeout: 0.3)
    }

    func testUnreachableServerIsATransportError() async {
        StubURLProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }

        do {
            let _: [Course] = try await client.get("/api/v1/courses")
            XCTFail("expected an error")
        } catch let error as APIError {
            XCTAssertEqual(error, .transport)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testUploadSendsTheFileAsMultipart() async throws {
        var contentType: String?
        var body = Data()
        respond(status: 202, json: """
        {"id": "3f2b8c4e-1d2a-4b5c-9e8f-7a6b5c4d3e2f",
         "course_id": "8a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", "filename": "appunti.pdf",
         "kind": "PDF", "size_bytes": 3, "status": "PROCESSING", "error_message": null,
         "page_count": null, "chunk_count": 0, "created_at": "2026-09-23T08:42:33.720Z"}
        """) { request in
            contentType = request.value(forHTTPHeaderField: "Content-Type")
            body = Self.body(of: request)
        }

        let document: CourseDocument = try await client.upload(
            "/api/v1/courses/x/documents", fileName: "appunti.pdf", data: Data("PDF".utf8)
        )

        XCTAssertEqual(document.status, .processing)
        XCTAssertTrue(contentType?.hasPrefix("multipart/form-data; boundary=") == true)
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"file\"; filename=\"appunti.pdf\""))
        XCTAssertTrue(text.contains("\r\n\r\nPDF\r\n--"))
    }

    func testMultipartFilenameCannotBreakTheHeader() {
        let body = APIClient.multipartBody(
            boundary: "B", fileName: "evil\"\r\nX-Injected: 1.pdf", data: Data()
        )
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains("filename=\"evil'X-Injected: 1.pdf\""))
        XCTAssertFalse(text.contains("\r\nX-Injected"))
    }

    func testDeleteAcceptsNoContent() async throws {
        var method: String?
        StubURLProtocol.handler = { request in
            method = request.httpMethod
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 204, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }

        try await client.delete("/api/v1/documents/x")

        XCTAssertEqual(method, "DELETE")
    }

    /// URLSession hands URLProtocol the body as a stream, not as httpBody.
    private static func body(of request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: buffer.count)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }

    func testCancelledRequestSurfacesAsCancellationNotAnError() async {
        StubURLProtocol.handler = { _ in throw URLError(.cancelled) }

        do {
            let _: [Course] = try await client.get("/api/v1/courses")
            XCTFail("expected an error")
        } catch is CancellationError {
            // expected: callers ignore cancellation instead of alerting the user
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }
}
