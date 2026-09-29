import SwiftUI

// User-facing names for server values, localized in Resources/Localizable.xcstrings.

extension StudyState {
    var label: String {
        switch self {
        case .notStudied: String(localized: "Not studied")
        case .studied: String(localized: "Studied")
        case .active: String(localized: "Active")
        case .paused: String(localized: "Paused")
        case .completed: String(localized: "Completed")
        case .unknown: String(localized: "Unknown")
        }
    }
}

extension MemoryState {
    var label: String {
        switch self {
        case .new: String(localized: "New")
        case .learning: String(localized: "Learning")
        case .review: String(localized: "In review")
        case .relearning: String(localized: "Relearning")
        case .mastered: String(localized: "Mastered")
        case .unknown: String(localized: "Unknown")
        }
    }
}

extension ReviewOutcome {
    var label: String {
        switch self {
        case .again: String(localized: "Again")
        case .hard: String(localized: "Hard")
        case .good: String(localized: "Good")
        case .easy: String(localized: "Easy")
        case .unknown: String(localized: "Unknown")
        }
    }

    /// What choosing this grade means, for the user's own grading.
    var explanation: String {
        switch self {
        case .again: String(localized: "I didn't know it")
        case .hard: String(localized: "I knew it, with difficulty")
        case .good: String(localized: "I knew it")
        case .easy: String(localized: "I knew it easily")
        case .unknown: ""
        }
    }

    var color: Color {
        switch self {
        case .again: .red
        case .hard: .orange
        case .good: .green
        case .easy: .blue
        case .unknown: .secondary
        }
    }
}

extension EvaluationClassification {
    var label: String {
        switch self {
        case .correct: String(localized: "Correct")
        case .partiallyCorrect: String(localized: "Partly correct")
        case .misconception: String(localized: "Misconception")
        case .wrong: String(localized: "Not correct")
        case .uncertain: String(localized: "Uncertain")
        case .unknown: String(localized: "Unknown")
        }
    }
}

extension LearningItemRole {
    var label: String {
        switch self {
        case .coreTrainable: String(localized: "Core")
        case .supportingTrainable: String(localized: "Supporting")
        case .commonTrap: String(localized: "Common trap")
        case .informational: String(localized: "Informational")
        case .reference: String(localized: "Reference")
        case .optionalExtension: String(localized: "Optional")
        case .unknown: String(localized: "Unknown")
        }
    }
}

extension SourceReference {
    /// "banca.pdf · p. 3 · Contratti bancari", from what the backend provides only.
    var summary: String {
        var parts = [documentName]
        if let pageNumber {
            parts.append(String(localized: "p. \(pageNumber)"))
        }
        if let section, !section.isEmpty {
            parts.append(section)
        }
        return parts.joined(separator: " · ")
    }
}

/// Shows a 0-1 estimate as a percentage, or a dash when there is none yet.
func percentText(_ value: Double?) -> String {
    guard let value else { return "—" }
    return value.formatted(.percent.precision(.fractionLength(0)))
}
