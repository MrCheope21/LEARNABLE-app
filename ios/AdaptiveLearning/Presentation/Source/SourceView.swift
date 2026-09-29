import SwiftUI

/// One source passage with where it comes from. Shows only what the backend provides.
struct SourceView: View {
    @State private var viewModel: SourceViewModel
    @Environment(\.dismiss) private var dismiss

    init(viewModel: SourceViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            LoadableView(state: viewModel.state, retry: viewModel.load) { passage in
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Label {
                            Text(verbatim: viewModel.reference.documentName)
                        } icon: {
                            Image(systemName: "doc.text")
                        }
                        .font(.headline)
                        if let page = passage.pageNumber {
                            Text("Page \(page)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        if let section = passage.section, !section.isEmpty {
                            Text(verbatim: section)
                                .font(.subheadline.weight(.semibold))
                        }
                        Divider()
                        Text(verbatim: passage.text)
                            .font(.body)
                            .textSelection(.enabled)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                }
            }
            .navigationTitle("Source")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                        .accessibilityIdentifier("source.done")
                }
            }
            .task { await viewModel.load() }
        }
    }
}

/// A tappable source line ("banca.pdf · p. 3 · Contratti") that opens the passage.
struct SourceRow: View {
    let reference: SourceReference
    let open: (SourceReference) -> Void

    var body: some View {
        Button {
            open(reference)
        } label: {
            Label {
                Text(verbatim: reference.summary)
                    .multilineTextAlignment(.leading)
            } icon: {
                Image(systemName: "doc.text.magnifyingglass")
            }
        }
        .accessibilityHint(Text("Opens the source passage"))
        .accessibilityIdentifier("source.row")
    }
}
