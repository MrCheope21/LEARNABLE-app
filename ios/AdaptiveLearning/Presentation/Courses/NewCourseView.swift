import SwiftUI

struct NewCourseView: View {
    @Bindable var viewModel: CoursesViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var language = CoursesViewModel.defaultLanguage

    var body: some View {
        NavigationStack {
            Form {
                TextField("Title", text: $title)
                Picker("Language", selection: $language) {
                    ForEach(CoursesViewModel.supportedLanguages, id: \.self) { code in
                        Text(verbatim: Locale.current.localizedString(forLanguageCode: code) ?? code)
                            .tag(code)
                    }
                }
            }
            .navigationTitle("New Course")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            if await viewModel.createCourse(title: title, language: language) {
                                dismiss()
                            }
                        }
                    }
                    .disabled(isTitleBlank || viewModel.isCreating)
                }
            }
            // Shown inside the sheet: an alert on the presenting view can't appear over it.
            .errorAlert($viewModel.createErrorMessage)
        }
    }

    private var isTitleBlank: Bool {
        title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
