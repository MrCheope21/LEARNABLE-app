import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";
import * as store from "./store";

const me = { id: "u1", email: "ada@example.com", timezone: "Europe/Rome", daily_goal: 20, language: "en", display_name: null };
const past = new Date(Date.now() - 3_600_000).toISOString();
const later = new Date(Date.now() + 2 * 86_400_000).toISOString();
const card = (id: string, question: string, due_at: string) => ({
  learning_item_id: id,
  question_formulation_id: `q-${id}`,
  question,
  expected_knowledge: `Answer to ${question}`,
  essential_points: [],
  due_at,
  drawing: false,
});
const pack = {
  course_id: "c1",
  title: "Diritto bancario",
  created_at: past,
  until: later,
  cards: [card("i1", "What is a loan?", past), card("i2", "What is a deposit?", later)],
};

describe("offline review", () => {
  it("downloads a course, asks what is due, keeps self-graded answers and sends them", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/auth\/me$/, ok(me)],
      ["GET", /\/courses\/c1\/offline-pack$/, ok(pack)],
      ["POST", /\/courses\/c1\/offline-sync$/, ok({ applied: 1, skipped: 0 })],
    ]);
    expect(await store.download("c1")).toBe(true);
    renderApp("/offline/c1");

    expect(await screen.findByRole("heading", { name: "What is a loan?" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your answer"), "money lent");
    await user.click(screen.getByRole("button", { name: "Show the answer" }));
    expect(screen.getByText("Answer to What is a loan?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Good" }));

    // Only the question due now was asked; the other can be reviewed ahead.
    expect(await screen.findByText("Nothing left to review offline right now.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review ahead/ })).toBeInTheDocument();
    expect(store.queue()).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Send now" }));
    await waitFor(() => expect(store.queue()).toHaveLength(0));
    const sent = requests.find((r) => r.path.endsWith("/offline-sync"));
    expect(sent?.body).toMatchObject({
      answers: [{ learning_item_id: "i1", question_formulation_id: "q-i1", text: "money lent", outcome: "GOOD" }],
    });
  });
});
