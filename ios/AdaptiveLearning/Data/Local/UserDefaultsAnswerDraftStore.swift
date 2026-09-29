import Foundation

/// Answer drafts in UserDefaults: small, local, survive the app being killed. Cleared as soon as
/// the backend has stored the answer.
struct UserDefaultsAnswerDraftStore: AnswerDraftStore {
    var defaults: UserDefaults = .standard
    private let prefix = "answerDraft."

    func load(key: String) -> String? {
        defaults.string(forKey: prefix + key)
    }

    func save(_ text: String, key: String) {
        defaults.set(text, forKey: prefix + key)
    }

    func clear(key: String) {
        defaults.removeObject(forKey: prefix + key)
    }
}
