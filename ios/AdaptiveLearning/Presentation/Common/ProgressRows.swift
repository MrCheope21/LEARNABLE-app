import SwiftUI

// Curriculum progress and memory progress are always shown as two separate things, never one
// score (docs/PROJECT_SPEC.md §54).

struct CurriculumProgressRows: View {
    let curriculum: CurriculumProgress

    var body: some View {
        LabeledContent("Concepts active") {
            Text("\(curriculum.active) of \(curriculum.concepts)")
        }
        LabeledContent("Studied") {
            Text(curriculum.studied, format: .number)
        }
        LabeledContent("Completed") {
            Text(curriculum.completed, format: .number)
        }
        if curriculum.paused > 0 {
            LabeledContent("Paused") {
                Text(curriculum.paused, format: .number)
            }
        }
    }
}

struct MemoryProgressRows: View {
    let memory: MemoryProgress

    var body: some View {
        LabeledContent {
            Text(verbatim: percentText(memory.mastery))
        } label: {
            Text("Mastery (estimate)")
        }
        LabeledContent("Items in training") {
            Text(memory.itemsTrained, format: .number)
        }
        LabeledContent("New / Learning / In review / Mastered") {
            Text(verbatim: "\(memory.new) / \(memory.learning) / \(memory.review + memory.relearning) / \(memory.mastered)")
                .monospacedDigit()
        }
        if memory.markedHard > 0 {
            LabeledContent("Marked hard") {
                Text(memory.markedHard, format: .number)
            }
        }
    }
}

struct ReviewLoadRows: View {
    let load: ReviewLoad

    var body: some View {
        LabeledContent("Due now") {
            Text(load.dueNow, format: .number)
        }
        if load.overdue > 0 {
            LabeledContent("Overdue") {
                Text(load.overdue, format: .number)
                    .foregroundStyle(.orange)
            }
        }
        LabeledContent("Today") {
            Text(load.today, format: .number)
        }
        LabeledContent("Tomorrow") {
            Text(load.tomorrow, format: .number)
        }
        LabeledContent("Next 7 days") {
            Text(load.next7Days, format: .number)
        }
        LabeledContent("New to learn") {
            Text(load.newToLearn, format: .number)
        }
    }
}
