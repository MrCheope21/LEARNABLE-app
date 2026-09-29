import { describe, expect, it } from "vitest";
import { pageLabel } from "./labels";

describe("pageLabel", () => {
  it("names one page, or a range when a passage continues onto later pages", () => {
    expect(pageLabel(8, null)).toBe("Page 8");
    expect(pageLabel(8, 9)).toBe("Pages 8–9");
    expect(pageLabel(8, 9, true)).toBe("pp. 8–9");
    expect(pageLabel(8, 8, true)).toBe("p. 8");
  });

  it("is empty for formats without pages", () => {
    expect(pageLabel(null, null)).toBeNull();
    expect(pageLabel(undefined, undefined)).toBeNull();
  });
});
