import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { SortableList } from "./SortableList";

// Dragging itself needs real layout, so it's covered in the browser (e2e/reorder.spec.ts).
const items = [
  { id: "a", title: "Alpha" },
  { id: "b", title: "Beta" },
  { id: "c", title: "Gamma" },
];

function renderList(disabledReason?: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SortableList
        items={items}
        itemLabel={(i) => i.title}
        onReorder={vi.fn(() => Promise.resolve())}
        renderItem={(i) => <span>{i.title}</span>}
        disabledReason={disabledReason}
      />
    </QueryClientProvider>,
  );
}

describe("SortableList", () => {
  it("renders the rows in order, each with a labelled drag handle", () => {
    renderList();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Alpha", "Beta", "Gamma"]);
    expect(screen.getAllByRole("button", { name: /^Reorder / }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Reorder Alpha",
      "Reorder Beta",
      "Reorder Gamma",
    ]);
  });

  it("hides the handles and explains why when reordering is disabled", () => {
    renderList("Clear the search to reorder these questions.");
    expect(screen.queryByRole("button", { name: /^Reorder / })).not.toBeInTheDocument();
    expect(screen.getByText("Clear the search to reorder these questions.")).toBeInTheDocument();
  });
});
