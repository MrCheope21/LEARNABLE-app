import Foundation

/// A server-defined value set that may grow. A value this app version doesn't know decodes as
/// `.unknown` instead of failing the whole response (the backend adds states over time).
protocol ResilientEnum: RawRepresentable, Codable, Hashable where RawValue == String {
    static var unknown: Self { get }
}

extension ResilientEnum {
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: raw) ?? Self.unknown
    }
}
