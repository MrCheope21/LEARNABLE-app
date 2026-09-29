import SwiftUI

struct SourcePassagesView: View {
    @State private var viewModel: SourcePassagesViewModel

    init(viewModel: SourcePassagesViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        List {
            ForEach(viewModel.passages) { passage in
                PassageRow(passage: passage)
                    .onAppear {
                        if passage.id == viewModel.passages.last?.id {
                            Task { await viewModel.loadMore() }
                        }
                    }
            }
            if viewModel.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
            }
        }
        .navigationTitle(Text(verbatim: viewModel.document.filename))
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadMore() }
        .errorAlert($viewModel.errorMessage)
    }
}

private struct PassageRow: View {
    let passage: SourcePassage

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let section = passage.section {
                Text(verbatim: section)
                    .font(.subheadline.weight(.semibold))
            }
            if let page = passage.pageNumber {
                Text("Page \(page)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(verbatim: passage.text)
                .font(.body)
                .textSelection(.enabled)
        }
        .padding(.vertical, 4)
    }
}
