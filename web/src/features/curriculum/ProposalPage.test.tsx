import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { renderApp } from "../../test/render";
import { PROPOSAL_POLL_MS } from "./ProposalPage";

const proposal = fixtures.proposal_ready;
const course = proposal.course_id;

function backend() {
  return mockApi([
    ["GET", /\/curriculum-proposals\/[^/]+$/, sequence(fixtures.proposal_generating, proposal)],
    ["POST", /\/curriculum-proposals\/[^/]+\/apply$/, () => ({ status: 201, body: fixtures.outline })],
    ["DELETE", /\/curriculum-proposals\/[^/]+$/, () => ({ status: 204 })],
    ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto bancario" })],
    ["GET", /\/courses\/[^/]+\/outline$/, ok(fixtures.outline)],
    ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
    ["GET", /\/courses\/[^/]+\/documents$/, ok([])],
  ]);
}

describe("curriculum proposal review", () => {
  beforeEach(() => {
    PROPOSAL_POLL_MS.value = 5;
  });

  it("waits for the AI, then applies the edited tree with the original sources", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/courses/${course}/proposals/${proposal.id}`);

    const topicTitle = await screen.findByLabelText("Topic title");
    await user.clear(topicTitle);
    await user.type(topicTitle, "Deposito");
    await user.click(screen.getByRole("button", { name: "+ Add concept" }));
    const conceptTitles = screen.getAllByLabelText("Concept title");
    await user.type(conceptTitles[conceptTitles.length - 1]!, "Restituzione");
    await user.click(screen.getByRole("button", { name: "Accept curriculum" }));

    await screen.findByRole("heading", { name: "Topics" });
    const body = requests.find((r) => r.path.endsWith("/apply"))?.body as Schemas["CurriculumApply"];
    const topic = body.topics![0]!;
    expect(body.chapters).toBeNull();
    expect(topic.title).toBe("Deposito");
    expect(topic.concepts!.map((c) => c.title).at(-1)).toBe("Restituzione");
    // AI concepts keep the passages they were tied to; a hand-added one has none.
    expect(topic.concepts![0]!.source_chunk_ids).toEqual(
      proposal.topics![0]!.concepts[0]!.sources.map((s) => s.chunk_id),
    );
    expect(topic.concepts!.at(-1)!.source_chunk_ids).toEqual([]);
  });

  it("refuses blank titles locally", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/courses/${course}/proposals/${proposal.id}`);

    await user.click(await screen.findByRole("button", { name: "+ Add concept" }));
    await user.click(screen.getByRole("button", { name: "Accept curriculum" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Every chapter, topic and concept needs a title.");
    expect(requests.some((r) => r.path.endsWith("/apply"))).toBe(false);
  });

  it("rejects the proposal", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/courses/${course}/proposals/${proposal.id}`);

    await user.click(await screen.findByRole("button", { name: "Reject proposal" }));

    await screen.findByRole("heading", { name: "Topics" });
    expect(requests.some((r) => r.method === "DELETE")).toBe(true);
  });
});
