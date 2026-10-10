import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const ADA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const BOB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

const me = { id: BOB, email: "bob@example.com", timezone: "Europe/Rome", daily_goal: 20, language: "en", display_name: "Bob", community_visible: true };

function board(overrides: Partial<Schemas["Leaderboard"]> = {}): Schemas["Leaderboard"] {
  const entries: Schemas["LeaderboardEntry"][] = [
    { rank: 1, user_id: ADA, name: "Ada", xp: 1200, is_me: false, following: false },
    { rank: 2, user_id: BOB, name: "Bob", xp: 600, is_me: true, following: false },
  ];
  return { period: "week", scope: "everyone", since: "2026-10-05T00:00:00Z", entries, me: entries[1]!, me_hidden: false, ...overrides };
}

function queryOf(fetchMock: { mock: { calls: unknown[][] } }, path: string) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(input instanceof Request ? input.url : String(input)))
    .filter((url) => url.pathname === path);
}

describe("community", () => {
  it("shows the leader with a link to their profile, and switches period and scope", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi([
      ["GET", /\/community\/leaderboard$/, ok(board())],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/community");

    const leader = await screen.findByRole("region", { name: "Leader" });
    expect(leader).toHaveTextContent("Ada");
    expect(leader).toHaveTextContent("1,200 XP");
    expect(screen.getAllByRole("link", { name: "Ada" })[0]).toHaveAttribute("href", `/community/users/${ADA}`);
    expect(screen.getByText("You")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "All time" }));
    await user.click(screen.getByRole("button", { name: "Friends" }));
    await waitFor(() => {
      const last = queryOf(fetchMock, "/api/v1/community/leaderboard").at(-1);
      expect(last?.searchParams.get("period")).toBe("all");
      expect(last?.searchParams.get("scope")).toBe("friends");
    });
  });

  it("invites someone who isn't visible to join, and joining turns it on", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/community\/leaderboard$/, ok(board({ entries: [], me: null, me_hidden: true }))],
      ["GET", /\/auth\/me$/, ok({ ...me, community_visible: false })],
      ["PATCH", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/community");

    expect(await screen.findByText("No one has earned XP in this period yet.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Show me in the community" }));
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ community_visible: true }));
  });

  it("asks for a display name before joining", async () => {
    mockApi([
      ["GET", /\/community\/leaderboard$/, ok(board({ entries: [], me: null, me_hidden: true }))],
      ["GET", /\/auth\/me$/, ok({ ...me, community_visible: false, display_name: null })],
    ]);
    renderApp("/community");
    expect(await screen.findByText(/Choose a display name in Settings first/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show me in the community" })).not.toBeInTheDocument();
  });

  it("follows someone from their profile", async () => {
    const user = userEvent.setup();
    const profile: Schemas["Profile"] = { user_id: ADA, name: "Ada", member_since: "2026-09-01T10:00:00Z", xp_total: 1200, xp_week: 300, streak: 9, followers: 4, following: 2, is_me: false, i_follow: false, follows_me: true };
    const { requests } = mockApi([
      ["GET", /\/community\/users\/[^/]+$/, ok(profile)],
      ["PUT", /\/community\/users\/[^/]+\/follow$/, ok({ ...profile, i_follow: true })],
    ]);
    renderApp(`/community/users/${ADA}`);

    expect(await screen.findByRole("heading", { name: "Ada" })).toBeInTheDocument();
    expect(screen.getByText("Follows you")).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Follow" }));
    await waitFor(() => expect(requests.some((r) => r.method === "PUT" && r.path === `/api/v1/community/users/${ADA}/follow`)).toBe(true));
  });

  it("says a hidden profile isn't available", async () => {
    mockApi([["GET", /\/community\/users\/[^/]+$/, () => ({ status: 404, body: { error_type: "not_found", message: "x", details: {} } })]]);
    renderApp(`/community/users/${ADA}`);
    expect(await screen.findByText("This profile isn't available.")).toBeInTheDocument();
  });

  it("searches learners by name on the Friends tab", async () => {
    const user = userEvent.setup();
    const person: Schemas["Person"] = { user_id: ADA, name: "Maria Rossi", xp_today: 40, streak: 3, last_active: null, i_follow: false, follows_me: false };
    const { fetchMock } = mockApi([
      ["GET", /\/community\/following$/, ok([])],
      ["GET", /\/community\/followers$/, ok([])],
      ["GET", /\/community\/people$/, ok([person])],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/community/friends");

    expect(await screen.findByText("You aren't following anyone yet.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Find learners by name"), "rossi");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("link", { name: "Maria Rossi" })).toBeInTheDocument();
    expect(queryOf(fetchMock, "/api/v1/community/people").at(-1)?.searchParams.get("q")).toBe("rossi");
  });
});
