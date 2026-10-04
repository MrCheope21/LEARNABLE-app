import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Tooltip, TOOLTIP_DELAY_MS } from "./Tooltip";

describe("tooltip", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function setUp() {
    render(
      <Tooltip text="Prepares this concept's questions.">
        <button type="button">Activate</button>
      </Tooltip>,
    );
    return { button: screen.getByRole("button", { name: "Activate" }), tip: screen.getByRole("tooltip", { hidden: true }) };
  }

  it("appears only after the pointer lingers, and hides when it leaves", () => {
    const { button, tip } = setUp();
    fireEvent.pointerEnter(button.parentElement!, { pointerType: "mouse" });
    act(() => void vi.advanceTimersByTime(TOOLTIP_DELAY_MS - 100));
    expect(tip).not.toHaveClass("visible");
    act(() => void vi.advanceTimersByTime(200));
    expect(tip).toHaveClass("visible");
    fireEvent.pointerLeave(button.parentElement!);
    expect(tip).not.toHaveClass("visible");
  });

  it("never shows for a quick pass or a click", () => {
    const { button, tip } = setUp();
    fireEvent.pointerEnter(button.parentElement!, { pointerType: "mouse" });
    fireEvent.pointerDown(button.parentElement!);
    act(() => void vi.advanceTimersByTime(TOOLTIP_DELAY_MS * 2));
    expect(tip).not.toHaveClass("visible");
  });

  it("describes the control for screen readers at once", () => {
    const { button } = setUp();
    expect(button).toHaveAccessibleDescription("Prepares this concept's questions.");
  });
});
