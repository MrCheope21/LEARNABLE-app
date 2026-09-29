import XCTest
@testable import AdaptiveLearning

final class APIDateFormatTests: XCTestCase {
    func testParsesBackendTimestampContract() throws {
        // Exact format the backend emits (docs/API.md) — pinned by the backend's
        // test_timestamps_follow_api_contract.
        let date = try XCTUnwrap(APIDateFormat.date(from: "2026-09-23T08:42:33.720Z"))
        XCTAssertEqual(date.timeIntervalSince1970, 1_790_152_953.72, accuracy: 0.001)
    }

    func testParsesTimestampWithoutFractionalSeconds() {
        XCTAssertNotNil(APIDateFormat.date(from: "2026-09-23T08:42:33Z"))
    }

    func testRejectsTimestampWithoutTimezone() {
        XCTAssertNil(APIDateFormat.date(from: "2026-09-23T08:42:33.720"))
    }

    func testDecoderDecodesSnakeCaseDates() throws {
        struct Payload: Decodable { let createdAt: Date }
        let json = Data(#"{"created_at": "2026-09-23T08:42:33.720Z"}"#.utf8)
        XCTAssertNoThrow(try JSONDecoder.apiDecoder.decode(Payload.self, from: json))
    }
}
