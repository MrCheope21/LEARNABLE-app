import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const base = { id: "u1", email: "boss@example.com", username: null, timezone: "UTC", daily_goal: 20, language: "en", display_name: null, community_visible: false };
const dashboardDown = () => ({ status: 503, body: { error_type: "internal_error", message: "x", details: {} } });

const member = {
  id: "u2",
  email: "marco@example.com",
  username: "marco",
  display_name: null,
  created_at: "2026-11-01T10:00:00.000Z",
  last_active_at: null,
  is_admin: false,
  is_active: true,
  course_count: 2,
  answer_count: 14,
  storage_bytes: 3 * 1024 * 1024,
  evaluations_today: 4,
  generations_today: 1,
  evaluations_limit: 100,
  generations_limit: 100,
  storage_limit_bytes: 500 * 1024 * 1024,
  custom_limits: false,
};

describe("admin", () => {
  it("sends someone who is not an administrator back home", async () => {
    mockApi([
      ["GET", /\/auth\/me$/, ok({ ...base, is_admin: false })],
      ["GET", /\/dashboard$/, dashboardDown],
    ]);
    renderApp("/admin");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Administration" })).not.toBeInTheDocument());
  });

  it("lists accounts with their usage, and suspends one", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/auth\/me$/, ok({ ...base, is_admin: true })],
      ["GET", /\/dashboard$/, dashboardDown],
      ["GET", /\/admin\/summary$/, ok({ users: 2, active_users: 2, ai_requests_today: 5, shared_daily_cap: 0, registration_open: false, default_evaluations: 100, default_generations: 100, default_storage_mb: 500 })],
      ["GET", /\/admin\/users$/, ok([{ ...member, id: "u1", email: "boss@example.com", is_admin: true, course_count: 7, answer_count: 90, evaluations_today: 9 }, member])],
      ["PATCH", /\/admin\/users\/u2$/, ok({ ...member, is_active: false })],
    ]);
    renderApp("/admin");

    expect(await screen.findByText("marco@example.com")).toBeInTheDocument();
    expect(screen.getByText(/2 courses · 14 answers · 3\.0 MB of material/)).toBeInTheDocument();
    expect(screen.getByText(/Today: 4 of 100 evaluations · 1 of 100 generations/)).toBeInTheDocument();
    // You can't suspend yourself: only the other account has the buttons.
    expect(screen.getAllByRole("button", { name: "Suspend" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Suspend" }));
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ is_active: false }));
  });

  it("creates an invitation and shows its link once", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/auth\/me$/, ok({ ...base, is_admin: true })],
      ["GET", /\/dashboard$/, dashboardDown],
      ["GET", /\/admin\/summary$/, ok({ users: 1, active_users: 1, ai_requests_today: 0, shared_daily_cap: 0, registration_open: false, default_evaluations: 100, default_generations: 100, default_storage_mb: 500 })],
      ["GET", /\/admin\/users$/, ok([])],
      ["GET", /\/admin\/invitations$/, ok([])],
      [
        "POST",
        /\/admin\/invitations$/,
        ok({ id: "i1", note: "Marco", email: null, status: "pending", created_at: "2026-11-08T10:00:00.000Z", expires_at: "2026-11-15T10:00:00.000Z", used_at: null, used_by_email: null, link: "https://learnable.duckdns.org/?invite=SECRETCODE" }),
      ],
    ]);
    renderApp("/admin");

    await user.click(await screen.findByRole("button", { name: "Invitations" }));
    await user.type(await screen.findByLabelText("Name or note"), "Marco");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(await screen.findByDisplayValue("https://learnable.duckdns.org/?invite=SECRETCODE")).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST")?.body).toMatchObject({ note: "Marco", days: 7 });
  });
});
