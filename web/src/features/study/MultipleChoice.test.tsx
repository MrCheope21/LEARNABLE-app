import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { renderApp } from "../../test/render";
import { shuffledOrder } from "./ChoicePicker";

const course = fixtures.session.course_id;
const choiceCard = {
  ...fixtures.card_learn,
  card: {
    ...fixtures.card_learn.card,
    introduction: null,
    answer_format: "CHOICE",
    choices: ["Il mutuante", "Il mutuatario", "La banca d'Italia"],
    multiple: false,
  },
};

describe("multiple choice", () => {
  it("shuffles the options the same way for the same question", () => {
    expect(shuffledOrder(4, "q1")).toEqual(shuffledOrder(4, "q1"));
    expect([...shuffledOrder(4, "q1")].sort()).toEqual([0, 1, 2, 3]);
  });

  it("answers by picking an option and sends its position", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["POST", /\/review-sessions$/, ok(fixtures.session)],
      ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(choiceCard, fixtures.card_done)],
      ["POST", /\/review-sessions\/[^/]+\/answers$/, ok(fixtures.answer_result)],
      ["POST", /\/review-sessions\/[^/]+\/end$/, ok(fixtures.session)],
      ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto", language: "it" })],
    ]);
    renderApp(`/study/${course}?intent=LEARN`);

    expect(await screen.findByText("Pick the right answer.")).toBeInTheDocument();
    const check = screen.getByRole("button", { name: "Check" });
    expect(check).toBeDisabled();
    // No text box for a multiple-choice question.
    expect(screen.queryByRole("textbox")).toBeNull();
    await user.click(screen.getByRole("radio", { name: /Il mutuatario/ }));
    await user.click(check);
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/answers"))).toBe(true));
    const sent = requests.find((r) => r.path.endsWith("/answers"));
    expect(sent?.body).toMatchObject({ choices: [1] });
  });
});
