import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { fixtures } from "../../test/fixtures";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const DRAWN = "data:image/png;base64,ZHJhd2luZw==";
const drawingCard = {
  ...fixtures.card_learn,
  card: { ...fixtures.card_learn.card!, introduction: null, answer_format: "DRAWING" },
};
const drawnResult = {
  ...fixtures.answer_result,
  text: "",
  has_drawing: true,
  reference: { ...fixtures.answer_result.reference, drawing: true },
};

beforeEach(() => {
  // jsdom has no canvas: a context that accepts the drawing calls, and a fixed export.
  const ctx = new Proxy({}, { get: () => vi.fn() });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue(DRAWN);
  URL.createObjectURL = vi.fn(() => "blob:drawing");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

function backend() {
  return mockApi([
    ["POST", /\/review-sessions$/, ok(fixtures.session)],
    ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(drawingCard, fixtures.card_done)],
    ["POST", /\/review-sessions\/[^/]+\/answers$/, ok(drawnResult)],
    ["GET", /\/answers\/[^/]+\/drawing$/, ok({})],
    ["GET", /\/learning-items\/[^/]+\/reference-drawing$/, ok({})],
    ["POST", /\/review-sessions\/[^/]+\/end$/, ok(fixtures.session)],
  ]);
}

describe("drawing questions", () => {
  it("are answered on the drawing pad and compared with the reference", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/study/${course}?intent=SCHEDULED_REVIEW`);

    const canvas = await screen.findByRole("img", { name: /Drawing area/ });
    expect(screen.queryByRole("button", { name: "Speak your answer" })).not.toBeInTheDocument();
    const submit = screen.getByRole("button", { name: /Submit/ });
    expect(submit).toBeDisabled();

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 40, clientY: 30, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(submit).toBeEnabled();
    await user.type(screen.getByLabelText("Note (optional)"), "con i doppi legami");
    await user.click(submit);

    const compare = await screen.findByRole("region", { name: "Your drawing and the reference" });
    expect(within(compare).getByRole("img", { name: "Your drawing" })).toHaveAttribute("src", "blob:drawing");
    expect(within(compare).getByRole("img", { name: "The reference drawing" })).toBeInTheDocument();
    const body = requests.find((r) => r.path.endsWith("/answers"))?.body;
    expect(body).toMatchObject({ drawing: DRAWN, text: "con i doppi legami" });
  });

  it("can be undone and cleared back to an empty answer", async () => {
    backend();
    renderApp(`/study/${course}?intent=SCHEDULED_REVIEW`);
    const canvas = await screen.findByRole("img", { name: /Drawing area/ });
    fireEvent.pointerDown(canvas, { clientX: 5, clientY: 5, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    const submit = screen.getByRole("button", { name: /Submit/ });
    expect(submit).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "↶ Undo" }));
    await waitFor(() => expect(submit).toBeDisabled());
  });
});
