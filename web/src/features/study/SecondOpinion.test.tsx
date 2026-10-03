import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failWith, mockApi, ok, sequence } from "../../test/mockApi";
import { fixtures } from "../../test/fixtures";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const secondOpinion = {
  ...fixtures.answer_result.evaluation,
  id: "second-opinion",
  classification: "PARTIALLY_CORRECT",
  correctness: 0.4,
  feedback: "Second look: only half of it.",
  user_argument: "I did mention the deposit.",
};

function backend(dispute: ReturnType<typeof ok> | ReturnType<typeof failWith>) {
  return mockApi([
    ["POST", /\/review-sessions$/, ok(fixtures.session)],
    ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(fixtures.card_learn, fixtures.card_done)],
    ["POST", /\/review-sessions\/[^/]+\/answers$/, ok(fixtures.answer_result)],
    ["POST", /\/answers\/[^/]+\/dispute$/, dispute],
    ["POST", /\/answers\/[^/]+\/override$/, ok(fixtures.override)],
    ["POST", /\/review-sessions\/[^/]+\/end$/, ok(fixtures.session)],
  ]);
}

async function answerAndDisagree() {
  const user = userEvent.setup();
  renderApp(`/study/${course}?intent=LEARN`);
  await user.click(await screen.findByRole("button", { name: /I'm ready/ }));
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.keyboard("{Control>}{Enter}{/Control}");
  await user.click(await screen.findByRole("button", { name: "Disagree with the grade?" }));
  return user;
}

describe("second opinion", () => {
  it("asks the AI again with the objection and keeps both evaluations visible", async () => {
    const { requests } = backend(ok({ ...fixtures.answer_result, second_opinion: secondOpinion }));
    const user = await answerAndDisagree();

    const ask = screen.getByRole("button", { name: "Ask for a second opinion" });
    expect(ask).toBeDisabled();
    await user.type(screen.getByLabelText("Why do you disagree?"), "I did mention the deposit.");
    await user.click(ask);

    const second = await screen.findByRole("region", { name: "Second opinion" });
    expect(within(second).getByText("Second look: only half of it.")).toBeInTheDocument();
    expect(within(second).getByText(/I did mention the deposit\./)).toBeInTheDocument();
    // The first evaluation is still there, and the grade buttons are still offered.
    const first = screen.getByRole("region", { name: "First evaluation" });
    expect(within(first).getByText(fixtures.answer_result.evaluation.feedback)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Hard/ })).toBeEnabled();
    expect(requests.find((r) => r.path.endsWith("/dispute"))?.body).toEqual({ argument: "I did mention the deposit." });
    expect(requests.some((r) => r.path.endsWith("/override"))).toBe(false);
  });

  it("explains a refused second opinion", async () => {
    backend(failWith(409, "conflict", "This answer already had the maximum number of second opinions."));
    const user = await answerAndDisagree();
    await user.type(screen.getByLabelText("Why do you disagree?"), "Please look again");
    await user.click(screen.getByRole("button", { name: "Ask for a second opinion" }));
    expect(await screen.findByText(/maximum number of second opinions/)).toBeInTheDocument();
  });
});
