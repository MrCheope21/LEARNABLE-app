import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, ok } from "../../test/mockApi";
import { fixtures } from "../../test/fixtures";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;
const spots = {
  concepts: [
    {
      concept_id: "c1",
      concept_title: "Deposito bancario",
      topic_title: "Contratti",
      chapter_title: "Banca",
      total: 3,
      misconceptions: [{ text: "Confonde deposito e mutuo", count: 2, last_seen: "2026-10-01T10:00:00Z" }],
    },
  ],
};

function open(body: unknown) {
  return mockApi([
    ["GET", /\/courses\/[^/]+\/weak-spots$/, ok(body)],
    ["GET", /\/courses\/[^/]+\/outline$/, ok(fixtures.outline)],
    ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
    ["GET", /\/courses\/[^/]+$/, ok(fixtures.courses[0])],
  ]);
}

describe("weak spots", () => {
  it("lists the misconceptions by concept with practice links", async () => {
    open(spots);
    renderApp(`/courses/${course}/weak-spots`);
    expect(await screen.findByRole("heading", { name: "What you keep getting wrong" })).toBeInTheDocument();
    const card = (await screen.findByText("Confonde deposito e mutuo")).closest("li.card") as HTMLElement;
    expect(within(card).getByText(/seen 2 times/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Practice this" })).toHaveAttribute(
      "href",
      expect.stringContaining("intent=PRACTICE&concepts=c1"),
    );
    expect(screen.getByRole("link", { name: /Practice the top 1 concept/ })).toBeInTheDocument();
  });

  it("says so when there is nothing to fix", async () => {
    open({ concepts: [] });
    renderApp(`/courses/${course}/weak-spots`);
    expect(await screen.findByText(/No recurring mistakes right now/)).toBeInTheDocument();
  });
});
