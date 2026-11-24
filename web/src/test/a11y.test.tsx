import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { violations } from "./axe";
import { mockApi, ok } from "./mockApi";
import { renderApp } from "./render";

const me = { id: "u1", email: "ada@example.com", username: null, is_admin: false, timezone: "Europe/Rome", daily_goal: 20, language: "en", display_name: null, community_visible: false };

describe("accessibility", () => {
  it("has no structural violations on the sign-in page", async () => {
    const { container } = renderApp("/", { signedIn: false });
    await screen.findByRole("heading", { name: /Sign in/ });
    expect(await violations(container)).toEqual([]);
  });

  it("has none on settings", async () => {
    mockApi([
      ["GET", /\/auth\/me$/, ok(me)],
      ["GET", /\/dashboard$/, () => ({ status: 503, body: { error_type: "internal_error", message: "x", details: {} } })],
    ]);
    const { container } = renderApp("/settings");
    await screen.findByRole("heading", { name: "Appearance" });
    expect(await violations(container)).toEqual([]);
  });
});
