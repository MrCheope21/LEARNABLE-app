import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

describe("progress", () => {
  it("shows curriculum and memory progress as separate figures, from the backend", async () => {
    const { requests } = mockApi([
      ["GET", /\/home$/, ok(fixtures.home)],
      ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
    ]);
    renderApp("/progress");

    const curriculum = (await screen.findByRole("heading", { name: "Curriculum" })).closest("section")!;
    const memory = screen.getByRole("heading", { name: "Memory" }).closest("section")!;
    expect(within(curriculum).getByText("1 of 1")).toBeInTheDocument();
    expect(within(memory).getByText("13%")).toBeInTheDocument();
    expect(within(curriculum).queryByText("13%")).toBeNull();
    // The user's own day boundaries are sent, not assumed.
    expect(requests.some((r) => r.path.endsWith("/progress"))).toBe(true);
  });
});
