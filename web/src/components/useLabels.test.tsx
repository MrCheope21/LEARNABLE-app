import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useLabels } from "./useLabels";

// Without a provider the interface is English.
const wrapper = ({ children }: { children: ReactNode }) => <>{children}</>;

describe("useLabels", () => {
  it("names one page, or a range when a passage continues onto later pages", () => {
    const { pageLabel } = renderHook(() => useLabels(), { wrapper }).result.current;
    expect(pageLabel(8, null)).toBe("Page 8");
    expect(pageLabel(8, 9)).toBe("Pages 8–9");
    expect(pageLabel(8, 9, true)).toBe("pp. 8–9");
    expect(pageLabel(8, 8, true)).toBe("p. 8");
  });

  it("is empty for formats without pages", () => {
    const { pageLabel } = renderHook(() => useLabels(), { wrapper }).result.current;
    expect(pageLabel(null, null)).toBeNull();
    expect(pageLabel(undefined, undefined)).toBeNull();
  });

  it("names the server's values and counts in singular and plural", () => {
    const labels = renderHook(() => useLabels(), { wrapper }).result.current;
    expect(labels.outcomeLabel.AGAIN).toBe("Again");
    expect(labels.studyStateLabel.NOT_STUDIED).toBe("Not studied");
    expect(labels.priorityLabel[1]).toBe("Essential");
    expect(labels.count("unit.question", 1)).toBe("1 question");
    expect(labels.count("unit.question", 5)).toBe("5 questions");
    expect(labels.priceLabel({ price_cents: 0, currency: "EUR" })).toBe("Free");
  });
});
