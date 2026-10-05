import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const LISTING_ID = "33333333-3333-3333-3333-333333333333";
const COURSE_ID = "44444444-4444-4444-4444-444444444444";

const summary: Schemas["ListingSummary"] = {
  id: LISTING_ID,
  title: "Diritto commerciale: l'imprenditore",
  subtitle: "Tutte le domande dell'orale",
  description: "Domande e risposte sull'imprenditore.",
  outcomes: ["Definire l'imprenditore"],
  audience: "Candidati all'esame da commercialista",
  level: "intermediate",
  category: "law",
  language: "it",
  tags: ["diritto"],
  author: "Prof. Rossi",
  price_cents: 0,
  currency: "EUR",
  version: 1,
  chapter_count: 2,
  item_count: 120,
  acquisition_count: 7,
  published_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
  status: "PUBLISHED",
  course_id: null,
};

const MANAGED_ID = fixtures.concept.course_id;

function managedCourse(id: string): Schemas["CourseRead"] {
  return {
    id,
    title: "Diritto commerciale: l'imprenditore",
    description: "",
    language: "it",
    paused: false,
    marketplace_listing_id: LISTING_ID,
    marketplace_version: 2,
    archived_at: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
  };
}

const detail: Schemas["ListingDetail"] = {
  ...summary,
  chapters: [
    { title: "L'imprenditore", questions: 70 },
    { title: "L'azienda", questions: 50 },
  ],
  is_mine: false,
  has_access: false,
};

describe("marketplace", () => {
  it("filters by category and level, and opens a course's page", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi([["GET", /\/marketplace\/listings$/, ok([summary])]]);
    renderApp("/marketplace");

    expect(await screen.findByText("Diritto commerciale: l'imprenditore")).toBeInTheDocument();
    expect(screen.getByText(/120 questions · 2 chapters · Intermediate · Italian/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Law/ }));
    await user.selectOptions(screen.getByLabelText("Level"), "intermediate");
    const browsed = () =>
      fetchMock.mock.calls
        .map(([input]) => new URL(input instanceof Request ? input.url : String(input)))
        .filter((url) => url.pathname === "/api/v1/marketplace/listings");
    await waitFor(() => {
      const last = browsed().at(-1);
      expect(last?.searchParams.get("category")).toBe("law");
      expect(last?.searchParams.get("level")).toBe("intermediate");
    });

    expect(screen.getByRole("link", { name: "Diritto commerciale: l'imprenditore" })).toHaveAttribute("href", `/marketplace/${LISTING_ID}`);
  });

  it("shows the sales page and size only, then adds the course to my courses", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/marketplace\/listings\/[^/]+$/, ok(detail)],
      ["POST", /\/marketplace\/listings\/[^/]+\/acquire$/, () => ({ status: 201, body: { course_id: COURSE_ID } })],
      ["GET", /\/courses\/[^/]+$/, ok(managedCourse(COURSE_ID))],
      ["GET", /\/courses\/[^/]+\/outline$/, ok([])],
      ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
    ]);
    renderApp(`/marketplace/${LISTING_ID}`);

    expect(await screen.findByRole("heading", { name: "Diritto commerciale: l'imprenditore" })).toBeInTheDocument();
    expect(screen.getByText("Definire l'imprenditore")).toBeInTheDocument();
    expect(screen.getByText("Candidati all'esame da commercialista")).toBeInTheDocument();
    expect(screen.getByText("70 questions")).toBeInTheDocument();
    expect(screen.getByText(/can't be downloaded/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add to my courses · Free" }));
    await waitFor(() =>
      expect(requests.some((r) => r.method === "POST" && r.path === `/api/v1/marketplace/listings/${LISTING_ID}/acquire`)).toBe(true),
    );
  });
});

describe("a course from the marketplace", () => {
  it("hides editing and lets me set my own priority", async () => {
    const user = userEvent.setup();
    const item = { ...fixtures.learning_items[0]!, priority: 1, origin_priority: 1 };
    const { requests } = mockApi([
      ["GET", /\/courses\/[^/]+$/, ok(managedCourse(MANAGED_ID))],
      ["GET", /\/courses\/[^/]+\/outline$/, ok(fixtures.outline)],
      ["GET", /\/courses\/[^/]+\/learning-items$/, ok([item])],
      ["PATCH", /\/learning-items\/[^/]+$/, ok({ ...item, priority: 3 })],
    ]);
    renderApp(`/courses/${MANAGED_ID}/questions`);

    expect(await screen.findByText(/its author keeps the questions up to date/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "All study material" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    const select = await screen.findByLabelText("Your priority");
    await user.selectOptions(select, "3");
    await waitFor(() => {
      const patch = requests.find((r) => r.method === "PATCH");
      expect(patch?.body).toEqual({ priority: 3 });
    });
  });
});
