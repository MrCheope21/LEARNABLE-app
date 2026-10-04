import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const COURSE_ID = "11111111-1111-1111-1111-111111111111";
const CONCEPT_ID = "22222222-2222-2222-2222-222222222222";

function card(overrides: Partial<Schemas["CourseCard"]> = {}): Schemas["CourseCard"] {
  return {
    id: COURSE_ID,
    title: "Diritto tributario: IRES e reddito d'impresa, con esercizi svolti e casi pratici",
    description: "Imposta sul reddito delle società",
    language: "it",
    paused: false,
    created_at: "2026-09-01T10:00:00Z",
    last_studied_at: "2026-09-24T18:00:00Z",
    concepts_total: 30,
    concepts_studied: 12,
    items_trained: 240,
    items_introduced: 84,
    due_now: 12,
    new_ready: 5,
    learn: { kind: "study", concept: { id: CONCEPT_ID, title: "Svalutazione crediti", study_state: "ACTIVE" }, session_id: null },
    ...overrides,
  };
}

function dashboardData(overrides: Partial<Schemas["Dashboard"]> = {}): Schemas["Dashboard"] {
  const days = ["2026-09-18", "2026-09-19", "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"];
  return {
    as_of: "2026-09-24T18:30:00Z",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    today: "2026-09-24",
    next_step: { kind: "review", course_id: COURSE_ID, course_title: "Diritto tributario", count: 12 },
    courses: [card(), card({ id: "33333333-3333-3333-3333-333333333333", title: "Banca", due_now: 0, created_at: "2026-09-20T10:00:00Z", last_studied_at: null, items_introduced: 0, learn: { kind: "activate", concept: { id: CONCEPT_ID, title: "Mutuo", study_state: "NOT_STUDIED" }, session_id: null } })],
    xp: { total: 1240, today: 60 },
    streak: { current: 5, today_complete: true, last_7_days: days.map((date, i) => ({ date, active: i > 1 })) },
    goal: { target: 20, done: 25, unit: "answers" },
    planner: {
      as_of: "2026-09-24T18:30:00Z",
      horizons: [
        { key: "now", due_by: "2026-09-24T18:30:00Z", items: 12 },
        { key: "1h", due_by: "2026-09-24T19:30:00Z", items: 14 },
        { key: "4h", due_by: "2026-09-24T22:30:00Z", items: 20 },
        { key: "1d", due_by: "2026-09-25T18:30:00Z", items: 31 },
        { key: "3d", due_by: "2026-09-27T18:30:00Z", items: 40 },
        { key: "7d", due_by: "2026-10-01T18:30:00Z", items: 55 },
      ],
    },
    activity: { start: "2026-07-06", end: "2026-09-27", today: "2026-09-24", days: [{ date: "2026-09-24", attempts: 25, xp: 60 }] },
    ...overrides,
  };
}

const me = { id: "u1", email: "ada@example.com", timezone: "Europe/Rome", daily_goal: 20 };

describe("dashboard", () => {
  it("shows the next step, course cards, and the personal widgets", async () => {
    mockApi([
      ["GET", /\/dashboard$/, ok(dashboardData())],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/");

    const next = await screen.findByRole("region", { name: "Review 12 items" });
    expect(within(next).getByRole("link", { name: "Start review" })).toHaveAttribute(
      "href",
      expect.stringContaining(`/study/${COURSE_ID}?intent=SCHEDULED_REVIEW`),
    );

    const first = screen.getAllByRole("article")[0]!;
    expect(within(first).getByText(/12/, { selector: "b" })).toBeInTheDocument();
    expect(within(first).getByText(/concepts studied/)).toBeInTheDocument();
    expect(within(first).getByText(/learning items introduced/)).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Review 12 items" })).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Learn next" })).toHaveAttribute("href", `/courses/${COURSE_ID}/concepts/${CONCEPT_ID}`);
    // A course with nothing due says so in plain text (not a dead button), and "Start learning" when activation is needed.
    const second = screen.getAllByRole("article")[1]!;
    expect(within(second).getByText("✓ Nothing to review now")).toBeInTheDocument();
    expect(within(second).queryByRole("link", { name: /Review/ })).not.toBeInTheDocument();
    expect(within(second).getByRole("link", { name: "Start learning" })).toBeInTheDocument();

    // Widgets: streak, XP, goal (count may exceed the target; the gauge caps), planner, activity.
    expect(screen.getByRole("region", { name: "Daily streak" })).toHaveTextContent("5");
    expect(screen.getByRole("region", { name: "Experience" })).toHaveTextContent("+60 XP today");
    expect(screen.getByText(/Daily goal: 25 of 20 completed answers today, 125 percent/)).toBeInTheDocument();
    const planner = screen.getByRole("table");
    expect(within(planner).getByRole("row", { name: /In 1 day 31/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See more" })).toHaveAttribute("href", "/activity");

    // Navigation: the logo goes home; streak and XP are in the bar.
    expect(screen.getByRole("link", { name: "LEARNABLE home" })).toHaveAttribute("href", "/");
    expect(screen.getByLabelText("Total experience: 1240 XP")).toBeInTheDocument();
  });

  it("filters, searches and sorts the library", async () => {
    const user = userEvent.setup();
    mockApi([
      ["GET", /\/dashboard$/, ok(dashboardData())],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/");
    await screen.findAllByRole("article");

    await user.selectOptions(screen.getByLabelText("Show"), "due");
    expect(screen.getAllByRole("article")).toHaveLength(1);
    await user.selectOptions(screen.getByLabelText("Show"), "all");
    await user.selectOptions(screen.getByLabelText("Sort by"), "alphabetical");
    expect(within(screen.getAllByRole("article")[0]!).getByText("Banca")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search courses"), "tributario");
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("resumes an unfinished consolidation first", async () => {
    mockApi([
      [
        "GET",
        /\/dashboard$/,
        ok(
          dashboardData({
            next_step: {
              kind: "resume_consolidation",
              course_id: COURSE_ID,
              course_title: "Diritto tributario",
              concept_id: CONCEPT_ID,
              concept_title: "Svalutazione crediti",
              session_id: "s-1",
              count: 5,
              round: 2,
              rounds_total: 3,
            },
          }),
        ),
      ],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/");
    const next = await screen.findByRole("region", { name: "Continue consolidation · Round 2 of 3" });
    expect(within(next).getByRole("link", { name: "Resume" })).toHaveAttribute("href", `/study/${COURSE_ID}?session=s-1`);
  });

  it("edits the daily goal with validation", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/dashboard$/, ok(dashboardData())],
      ["GET", /\/auth\/me$/, ok(me)],
      ["PATCH", /\/auth\/me$/, ok({ ...me, daily_goal: 30 })],
    ]);
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Edit goal" }));
    const input = screen.getByLabelText("Answers per day");
    await user.clear(input);
    await user.type(input, "0");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "30");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ daily_goal: 30 }));
  });

  it("says when there is no course yet", async () => {
    mockApi([
      ["GET", /\/dashboard$/, ok(dashboardData({ courses: [], next_step: { kind: "create_course" } }))],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/");
    expect(await screen.findByText("Start your first course")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create your first course" })).toBeInTheDocument();
  });

  it("signing out clears cached data and saved drafts", async () => {
    const user = userEvent.setup();
    localStorage.setItem("learnable.draft.question.q1", "private answer");
    mockApi([
      ["GET", /\/dashboard$/, ok(dashboardData())],
      ["GET", /\/auth\/me$/, ok(me)],
    ]);
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem("learnable.draft.question.q1")).toBeNull();
    expect(localStorage.getItem("learnable.accessToken")).toBeNull();
    expect(screen.queryByText("Diritto tributario")).not.toBeInTheDocument();
  });
});
