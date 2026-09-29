import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const session: Schemas["SessionRead"] = {
  ...fixtures.session,
  id: "batch-1",
  intent: "CONSOLIDATION",
  selection_mode: "CONSOLIDATION",
  total: 3,
  position: 1,
  xp_earned: 10,
};
const baseCard = fixtures.card_learn.card!;
const round2: Schemas["SessionCard"] = {
  session,
  done: false,
  card: {
    ...baseCard,
    introduction: null,
    pending_answer_id: null,
    round: 2,
    rounds_total: 3,
    potential_xp: { eligible: true, ordinal: 2, xp: 20, xp_with_hint: 10 },
    hint: { available: true, revealed: false, text: null },
  },
};
const answered: Schemas["AnswerResult"] = {
  ...fixtures.answer_result,
  intent: "CONSOLIDATION",
  consolidation_round: 2,
  hint_used: true,
  session: { ...session, position: 2, xp_earned: 20 },
  xp: { reason: "INITIAL", correct: true, ordinal: 2, base_xp: 20, hint_used: true, xp: 10 },
};

describe("consolidation", () => {
  it("resumes the stored batch, shows the round and XP, and halves XP after a confirmed hint", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/review-sessions\/batch-1$/, ok(session)],
      ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(round2)],
      ["POST", /\/review-sessions\/[^/]+\/hint$/, ok({ available: true, revealed: true, text: "consegna…" })],
      ["POST", /\/review-sessions\/[^/]+\/answers$/, ok(answered)],
      ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto bancario" })],
    ]);
    renderApp(`/study/${course}?session=batch-1`);

    expect(await screen.findByText("Round 2 of 3")).toBeInTheDocument();
    // Resumed, not recreated.
    expect(requests.some((r) => r.method === "POST" && r.path.endsWith("/review-sessions"))).toBe(false);
    expect(screen.getByText(/Correct answer: \+20 XP/)).toBeInTheDocument();

    // The halving is stated before anything is revealed; cancelling reveals nothing.
    await user.click(screen.getByRole("button", { name: "Show hint" }));
    expect(screen.getByText("Using a hint halves the XP for this answer.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(requests.some((r) => r.path.endsWith("/hint"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "Show hint" }));
    await user.click(screen.getByRole("button", { name: "Reveal hint" }));
    expect(await screen.findByText("consegna…")).toBeInTheDocument();
    expect(screen.getByText(/Correct answer: \+10 XP/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Your answer"), "La consegna di denaro");
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(await screen.findByText(/Correct · \+10 XP · Hint used/)).toBeInTheDocument();
    // The client never sends an XP amount or a correctness claim.
    const answer = requests.find((r) => r.path.endsWith("/answers"));
    expect(answer?.body).toEqual({ question_formulation_id: baseCard.question.id, text: "La consegna di denaro", method: "TEXT" });
    await waitFor(() => expect(screen.getByLabelText("20 XP this session")).toBeInTheDocument());
    // Leaving keeps the batch open to resume.
    expect(screen.getByRole("button", { name: "Leave (resume later)" })).toBeInTheDocument();
  });
});
