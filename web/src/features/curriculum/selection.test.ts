import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { removalFor } from "./selection";

const concept = (id: string) => ({ id, title: id }) as Schemas["TopicOutline"]["concepts"][number];
const topic = (id: string, concepts: string[]) => ({ id, title: id, concepts: concepts.map(concept) }) as Schemas["TopicOutline"];
const chapters = [
  { id: "c1", title: "c1", topics: [topic("t1", ["k1", "k2"]), topic("t2", ["k3"])] },
  { id: "c2", title: "c2", topics: [topic("t3", ["k4"])] },
] as Schemas["ChapterOutline"][];
const item = (id: string, concept_id: string) => ({ id, concept_id }) as Schemas["LearningItemRead"];
const items = [item("i1", "k1"), item("i2", "k1"), item("i3", "k2"), item("i4", "k3"), item("i5", "k4")];

describe("removalFor", () => {
  it("removes a chapter whose questions are all selected, not its parts", () => {
    expect(removalFor(chapters, items, new Set(["i1", "i2", "i3", "i4"]))).toEqual({
      chapterIds: ["c1"],
      topicIds: [],
      conceptIds: [],
      itemIds: [],
    });
  });

  it("removes a topic or a concept when only that group is covered", () => {
    expect(removalFor(chapters, items, new Set(["i1", "i2", "i3"]))).toEqual({
      chapterIds: [],
      topicIds: ["t1"],
      conceptIds: [],
      itemIds: [],
    });
    expect(removalFor(chapters, items, new Set(["i1", "i2"]))).toEqual({
      chapterIds: [],
      topicIds: [],
      conceptIds: ["k1"],
      itemIds: [],
    });
  });

  it("keeps a group when a question in it is not selected", () => {
    expect(removalFor(chapters, items, new Set(["i1"]))).toEqual({
      chapterIds: [],
      topicIds: [],
      conceptIds: [],
      itemIds: ["i1"],
    });
  });

  it("mixes groups and loose questions, and ignores groups with no questions", () => {
    const withEmpty = [...chapters, { id: "c3", title: "c3", topics: [topic("t4", ["k5"])] }] as Schemas["ChapterOutline"][];
    expect(removalFor(withEmpty, items, new Set(["i5", "i4"]))).toEqual({
      chapterIds: ["c2"],
      topicIds: ["t2"],
      conceptIds: [],
      itemIds: [],
    });
    expect(removalFor(withEmpty, items, new Set())).toEqual({ chapterIds: [], topicIds: [], conceptIds: [], itemIds: [] });
  });
});
