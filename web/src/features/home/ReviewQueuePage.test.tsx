import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const COURSE = "11111111-1111-4111-8111-111111111111";
const me = { id: "u1", email: "ada@example.com", username: null, is_admin: false, timezone: "Europe/Rome", daily_goal: 20, language: "en", display_name: null, community_visible: false };
const row = (id: string, question: string, concept: string, topic: string, extra = {}) => ({
  learning_item_id: id,
  question,
  chapter_id: "c1",
  chapter_title: "Contratti",
  topic_id: `t-${topic}`,
  topic_title: topic,
  concept_id: `k-${concept}`,
  concept_title: concept,
  level: 2,
  marked_hard: false,
  overdue_days: 0,
  current: false,
  ...extra,
});
const queue = {
  total: 3,
  items: [
    row("a1", "Che cos'è il mutuo?", "Mutuo", "Prestiti", { overdue_days: 2 }),
    row("a2", "Chi sono le parti del mutuo?", "Mutuo", "Prestiti", { marked_hard: true }),
    row("b1", "Cos'è il deposito?", "Deposito", "Banca"),
  ],
};

function backend() {
  return mockApi([
    ["GET", /\/auth\/me$/, ok(me)],
    ["GET", /\/dashboard$/, () => ({ status: 503, body: { error_type: "internal_error", message: "x", details: {} } })],
    ["GET", /\/courses\/[^/]+$/, ok({ id: COURSE, title: "Diritto" })],
    ["GET", /\/courses\/[^/]+\/review-queue$/, ok(queue)],
  ]);
}

describe("choose what to review", () => {
  it("lists the due questions by chapter and topic, in course order", async () => {
    backend();
    renderApp(`/review/${COURSE}`);
    expect(await screen.findByRole("heading", { name: "Contratti" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prestiti" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Banca" })).toBeInTheDocument();
    // One box per question, one per topic, one for the chapter.
    expect(screen.getAllByRole("checkbox")).toHaveLength(6);
    expect(screen.getByText("2 days late")).toBeInTheDocument();
    expect(screen.getByText("Hard")).toBeInTheDocument();
    // Nothing ticked: the bar offers the whole review.
    expect(screen.getByRole("link", { name: "Review all (3)" })).toHaveAttribute("href", expect.stringContaining("intent=SCHEDULED_REVIEW"));
  });

  it("reviews only the ticked questions, a whole topic at once", async () => {
    const user = userEvent.setup();
    backend();
    renderApp(`/review/${COURSE}`);
    await screen.findByRole("heading", { name: "Contratti" });

    await user.click(screen.getByRole("checkbox", { name: "Select Prestiti" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    const review = screen.getByRole("link", { name: "Review 2 selected" });
    const href = review.getAttribute("href") ?? "";
    expect(href).toContain("intent=SCHEDULED_REVIEW");
    expect(href).toContain("items=a1%2Ca2");

    // Untick one question: just that one stays.
    await user.click(within(screen.getByText("Chi sono le parti del mutuo?").closest("label")!).getByRole("checkbox"));
    expect(screen.getByRole("link", { name: "Review 1 selected" }).getAttribute("href")).toContain("items=a1");
  });

  it("filters by marked hard and by search", async () => {
    const user = userEvent.setup();
    backend();
    renderApp(`/review/${COURSE}`);
    await screen.findByRole("heading", { name: "Contratti" });
    await user.click(screen.getByRole("button", { name: "Marked hard" }));
    expect(screen.getByText("Chi sono le parti del mutuo?")).toBeInTheDocument();
    expect(screen.queryByText("Cos'è il deposito?")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "All" }));
    await user.type(screen.getByRole("searchbox", { name: "Search questions" }), "deposito");
    expect(screen.getByText("Cos'è il deposito?")).toBeInTheDocument();
    expect(screen.queryByText("Che cos'è il mutuo?")).not.toBeInTheDocument();
  });
});
