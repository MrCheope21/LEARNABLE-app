import SwiftUI

struct CourseDetailView: View {
    @State private var viewModel: CourseDetailViewModel

    init(viewModel: CourseDetailViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        List {
            Section {
                if viewModel.documents.isEmpty && viewModel.hasLoaded {
                    Text("Import your study material: PDF, Word, PowerPoint, text or Markdown.")
                        .foregroundStyle(.secondary)
                }
                ForEach(viewModel.documents) { document in
                    if document.status == .ready {
                        NavigationLink(value: document) {
                            DocumentRow(document: document)
                        }
                    } else {
                        // Not a link: group its texts into one element for VoiceOver.
                        DocumentRow(document: document)
                            .accessibilityElement(children: .combine)
                    }
                }
                .onDelete { offsets in
                    let targets = offsets.map { viewModel.documents[$0] }
                    Task {
                        for document in targets {
                            await viewModel.delete(document)
                        }
                    }
                }
            } header: {
                Text("Study Material")
            }
        }
        .navigationTitle(viewModel.chapterId == nil ? Text("All Study Material") : Text("Chapter Material"))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    viewModel.isImporting = true
                } label: {
                    Label("Import", systemImage: "square.and.arrow.down")
                }
                .disabled(viewModel.isUploading)
            }
        }
        .fileImporter(
            isPresented: $viewModel.isImporting,
            allowedContentTypes: CourseDetailViewModel.importableTypes
        ) { result in
            switch result {
            case .success(let url):
                Task { await viewModel.importFile(at: url) }
            case .failure:
                viewModel.errorMessage = String(localized: "The file couldn't be read.")
            }
        }
        .overlay {
            if viewModel.isUploading {
                ProgressView("Uploading…")
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .refreshable { await viewModel.load() }
        .task {
            await viewModel.load()
            await viewModel.refreshUntilProcessed()
        }
        .errorAlert($viewModel.errorMessage)
    }
}

private struct DocumentRow: View {
    let document: CourseDocument

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(verbatim: document.filename)
                .font(.headline)
                .lineLimit(2)
            switch document.status {
            case .processing:
                HStack(spacing: 6) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Processing…")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            case .ready:
                Text(readySummary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case .failed:
                Label {
                    if let reason = document.errorMessage {
                        // The backend's reason, shown as-is.
                        Text(verbatim: reason)
                    } else {
                        Text("Processing failed")
                    }
                } icon: {
                    Image(systemName: "exclamationmark.triangle")
                }
                .font(.caption)
                .foregroundStyle(.orange)
            }
        }
        // Grouped by the caller when it isn't inside a NavigationLink (see the list above).
    }

    private var readySummary: LocalizedStringKey {
        if let pages = document.pageCount {
            return "Pages: \(pages) · Passages: \(document.chunkCount)"
        }
        return "Passages: \(document.chunkCount)"
    }
}
