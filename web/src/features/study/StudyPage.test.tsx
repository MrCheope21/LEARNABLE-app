import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failWith, mockApi, ok, sequence } from "../../test/mockApi";
import { fixtures } from "../../test/fixtures";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const questionId = fixtures.card_learn.card!.question.id;
const draftKey = `learnable.draft.question.${questionId}`;

function learnBackend(answer: ReturnType<typeof ok> | ReturnType<typeof failWith> = ok(fixtures.answer_result)) {
  return mockApi([
    ["POST", /\/review-sessions$/, ok(fixtures.session)],
    ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(fixtures.card_learn, fixtures.card_done)],
    ["POST", /\/review-sessions\/[^/]+\/answers$/, answer],
    ["POST", /\/answers\/[^/]+\/override$/, ok(fixtures.override)],
    ["POST", /\/review-sessions\/[^/]+\/end$/, ok(fixtures.session)],
    ["GET", /\/documents\/[^/]+\/chunks\/[^/]+$/, ok(fixtures.chunk)],
  ]);
}

describe("study session", () => {
  it("runs LEARN end to end: introduction, recall, feedback, override, finish", async () => {
    const user = userEvent.setup();
    const { requests } = learnBackend();
    renderApp(`/study/${course}?intent=LEARN&concepts=${fixtures.card_learn.card!.concept_id}`);

    // The introduction comes first, with its source.
    await screen.findByText("New material");
    const created = requests.find((r) => r.method === "POST" && r.path.endsWith("/review-sessions"));
    expect(created?.body).toMatchObject({ intent: "LEARN", concept_ids: [fixtures.card_learn.card!.concept_id] });
    await user.click(screen.getByRole("button", { name: /banca\.md/ }));
    expect(await screen.findByLabelText("Source passage")).toHaveTextContent(fixtures.chunk.text);

    await user.click(screen.getByRole("button", { name: /I'm ready/ }));
    const editor = screen.getByLabelText("Your answer");
    await user.type(editor, "La banca acquista la proprieta del denaro");
    // Saved locally on every change.
    expect(localStorage.getItem(draftKey)).toBe("La banca acquista la proprieta del denaro");

    await user.keyboard("{Control>}{Enter}{/Control}");

    // The backend's evaluation, reference and schedule are shown as returned.
    expect(await screen.findByText("Good")).toBeInTheDocument();
    // The evaluation is a breakdown and a checklist, not one grade.
    expect(screen.getByRole("list", { name: "Score breakdown" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "What your answer covered" })).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/Next review:/)).toBeInTheDocument();
    expect(localStorage.getItem(draftKey)).toBeNull();
    const answer = requests.find((r) => r.path.endsWith("/answers"));
    expect(answer?.body).toEqual({
      question_formulation_id: questionId,
      text: "La banca acquista la proprieta del denaro",
      method: "TEXT",
    });

    // Disagree: the user's grade is stored beside the AI evaluation, which stays.
    await user.click(screen.getByRole("button", { name: "Disagree with the grade?" }));
    await user.click(screen.getByRole("button", { name: /^Hard/ }));
    expect(await screen.findByText("Graded by you")).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/override"))?.body).toEqual({ outcome: "HARD" });
    expect(screen.getByText(/AI evaluation: Correct/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    expect(screen.getByText("Hard: 1")).toBeInTheDocument();
  });

  it("keeps the answer in the editor and on disk when submitting fails", async () => {
    const user = userEvent.setup();
    learnBackend(failWith(503, "ai_unavailable"));
    renderApp(`/study/${course}?intent=LEARN`);

    await user.click(await screen.findByRole("button", { name: /I'm ready/ }));
    await user.type(screen.getByLabelText("Your answer"), "Una risposta importante");
    await user.click(screen.getByRole("button", { name: /Submit/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI is temporarily unavailable");
    expect(screen.getByLabelText("Your answer")).toHaveValue("Una risposta importante");
    expect(localStorage.getItem(draftKey)).toBe("Una risposta importante");
  });

  it("restores a draft typed before the page was closed", async () => {
    localStorage.setItem(draftKey, "Half-typed answer");
    learnBackend();
    const user = userEvent.setup();
    renderApp(`/study/${course}?intent=LEARN`);

    await user.click(await screen.findByRole("button", { name: /I'm ready/ }));
    expect(screen.getByLabelText("Your answer")).toHaveValue("Half-typed answer");
  });

  it("shows nothing-to-study as an empty state, not an error", async () => {
    mockApi([["POST", /\/review-sessions$/, failWith(409, "conflict", "There is nothing to study")]]);
    renderApp(`/study/${course}?intent=SCHEDULED_REVIEW`);

    expect(await screen.findByText("Nothing to study right now")).toBeInTheDocument();
  });

  it("brings back an answer still waiting for a grade and grades it from the keyboard", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["POST", /\/review-sessions$/, ok(fixtures.session)],
      ["GET", /\/review-sessions\/[^/]+\/next$/, ok(fixtures.card_pending)],
      ["GET", /\/answers\/[^/]+$/, ok(fixtures.answer_failed)],
      ["POST", /\/answers\/[^/]+\/override$/, ok(fixtures.override)],
    ]);
    renderApp(`/study/${course}?intent=PRACTICE&mode=MARKED_HARD`);

    expect(await screen.findByText("How well did you know it?")).toBeInTheDocument();
    expect(screen.getByText(fixtures.answer_failed.evaluation!.error_message!)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try the evaluation again/ })).toBeInTheDocument();

    await user.keyboard("2");
    await waitFor(() => expect(requests.find((r) => r.path.endsWith("/override"))?.body).toEqual({ outcome: "HARD" }));
  });
});
