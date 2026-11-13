import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const session = { ...fixtures.session, intent: "SCHEDULED_REVIEW", total: 3, position: 0 };
const second = {
  ...fixtures.card_learn,
  card: { ...fixtures.card_learn.card!, learning_item_id: "b1", introduction: null, question: { ...fixtures.card_learn.card!.question, id: "q-b1", text: "Cos'è il deposito?" } },
};
const first = { ...fixtures.card_learn, card: { ...fixtures.card_learn.card!, introduction: null }, session };
const row = (id: string, question: string, current = false) => ({
  learning_item_id: id, question, chapter_id: "c1", chapter_title: "Contratti", topic_id: "t1", topic_title: "Prestiti",
  concept_id: "k1", concept_title: "Mutuo", level: 1, marked_hard: false, overdue_days: 0, current,
});

describe("choosing the next question during a review", () => {
  it("lists what is left and makes the chosen question the next one", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["POST", /\/review-sessions$/, ok(session)],
      ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(first, second)],
      ["GET", /\/review-sessions\/[^/]+\/queue$/, ok({ total: 3, items: [row("a1", "Che cos'è il mutuo?", true), row("a2", "Chi sono le parti?"), row("b1", "Cos'è il deposito?")] })],
      ["POST", /\/review-sessions\/[^/]+\/pick$/, ok(second)],
    ]);
    renderApp(`/study/${course}?intent=SCHEDULED_REVIEW`);

    await user.click(await screen.findByRole("button", { name: "Questions · 3 left" }));
    const panel = await screen.findByRole("complementary", { name: "Questions" });
    expect(within(panel).getByText("Contratti")).toBeInTheDocument();
    // The one on screen is marked and can't be picked again.
    expect(within(panel).getByRole("button", { name: /Che cos'è il mutuo\?/ })).toBeDisabled();

    await user.click(within(panel).getByRole("button", { name: /Cos'è il deposito\?/ }));
    expect(await screen.findByRole("heading", { name: "Cos'è il deposito?" })).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/pick"))?.body).toEqual({ learning_item_id: "b1" });
    expect(screen.queryByRole("complementary", { name: "Questions" })).not.toBeInTheDocument();
  });

  it("is not offered while consolidating", async () => {
    mockApi([
      ["GET", /\/review-sessions\/[^/]+$/, ok({ ...session, intent: "CONSOLIDATION" })],
      ["GET", /\/review-sessions\/[^/]+\/next$/, ok({ ...first, session: { ...session, intent: "CONSOLIDATION" } })],
    ]);
    renderApp(`/study/${course}?session=${session.id}`);
    await screen.findByLabelText("Your answer");
    expect(screen.queryByRole("button", { name: /Questions ·/ })).not.toBeInTheDocument();
  });
});
