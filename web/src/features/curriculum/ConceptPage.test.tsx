import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { renderApp } from "../../test/render";
import { GENERATION_POLL_MS } from "./ConceptPage";

const concept = fixtures.concept;
const notStudied = { ...concept, study_state: "NOT_STUDIED", item_generation_status: "NONE", is_reviewable: false };
const newItems = fixtures.learning_items.map((item) => ({
  ...item,
  review_state: { ...item.review_state, state: "NEW" as const, level: 0 },
}));

const plan = {
  concept_id: concept.id,
  concept_active: true,
  unfinished: null,
  unfinished_items: 0,
  new_items: 1,
  batch_items: 1,
  rounds_per_item: 3,
  answers_in_batch: 3,
  remaining_after_batch: 0,
};

describe("concept activation", () => {
  beforeEach(() => {
    GENERATION_POLL_MS.value = 5;
  });

  it("activates, follows item generation, then offers consolidation", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/concepts\/[^/]+$/, sequence(notStudied, fixtures.concept_activated, concept)],
      ["POST", /\/concepts\/[^/]+\/activate$/, ok(fixtures.concept_activated)],
      ["GET", /\/concepts\/[^/]+\/learning-items$/, sequence([], newItems)],
      ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
      ["GET", /\/courses\/[^/]+$/, ok({ id: concept.course_id, title: "Diritto bancario" })],
      ["GET", /\/courses\/[^/]+\/outline$/, ok(fixtures.outline)],
      ["GET", /\/home$/, ok(fixtures.home)],
      ["GET", /\/concepts\/[^/]+\/consolidation$/, ok(plan)],
      ["POST", /\/concepts\/[^/]+\/consolidation$/, ok({ ...fixtures.session, id: "resumable-batch", intent: "CONSOLIDATION" })],
    ]);
    renderApp(`/courses/${concept.course_id}/concepts/${concept.id}`);

    await user.click(await screen.findByRole("button", { name: "Activate" }));

    // The batch is described before it starts: items, rounds, answers.
    expect(await screen.findByText(/1 item · 3 answers/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "I have studied this concept" }));
    await waitFor(() =>
      expect(requests.filter((r) => r.method === "POST").map((r) => r.path)).toEqual([
        `/api/v1/concepts/${concept.id}/activate`,
        `/api/v1/concepts/${concept.id}/consolidation`,
      ]),
    );
    // Polled while GENERATING, stopped when READY.
    expect(requests.filter((r) => r.method === "GET" && r.path === `/api/v1/concepts/${concept.id}`).length).toBeGreaterThanOrEqual(2);
  });
});
