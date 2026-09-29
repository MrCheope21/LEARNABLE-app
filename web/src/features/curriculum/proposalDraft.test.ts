import { describe, expect, it } from "vitest";
import { fixtures } from "../../test/fixtures";
import { applyBody, blankConcept, draftFrom, mergeWithNext, move, moveConcept } from "./proposalDraft";

describe("proposal draft edits", () => {
  const draft = () => draftFrom(fixtures.proposal_ready);

  it("reorders", () => {
    expect(move([1, 2, 3], 0, 2)).toEqual([2, 3, 1]);
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });

  it("merges two concepts keeping every source once", () => {
    const { topics } = draft();
    const concepts = [...topics[0]!.concepts, { ...topics[0]!.concepts[0]!, key: "copy", title: "Copy" }];
    const merged = mergeWithNext(concepts, concepts.length - 2);
    expect(merged).toHaveLength(concepts.length - 1);
    const ids = merged.at(-1)!.sources.map((s) => s.chunk_id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("moves a concept between topics", () => {
    const { topics } = draft();
    const second = { ...topics[0]!, key: "t2", title: "Second", existingTopicId: null, concepts: [blankConcept()] };
    const conceptKey = topics[0]!.concepts[0]!.key;
    const moved = moveConcept([topics[0]!, second], conceptKey, "t2");
    expect(moved[0]!.concepts.some((c) => c.key === conceptKey)).toBe(false);
    expect(moved[1]!.concepts.at(-1)!.key).toBe(conceptKey);
    const applied = applyBody(null, moved).topics?.[1]?.concepts?.at(-1);
    expect(applied?.source_chunk_ids?.length).toBeGreaterThan(0);
  });
});
