import type { Schemas } from "../../api/client";

type Chapter = Schemas["ChapterOutline"];
type Item = Schemas["LearningItemRead"];

export type Removal = {
  chapterIds: string[];
  topicIds: string[];
  conceptIds: string[];
  /** Selected questions that are not inside a group being removed. */
  itemIds: string[];
};

/**
 * What deleting the selection removes: the selected questions, and every chapter, topic or concept
 * whose questions are all selected (a group with no questions at all is left alone, and empty
 * concepts inside a removed group go with it). Only the outermost groups are listed.
 */
export function removalFor(chapters: Chapter[], items: Item[], selected: Set<string>): Removal {
  const byConcept = new Map<string, string[]>();
  for (const item of items) byConcept.set(item.concept_id, [...(byConcept.get(item.concept_id) ?? []), item.id]);
  const covered = (ids: string[]) => ids.length > 0 && ids.every((id) => selected.has(id));
  const result: Removal = { chapterIds: [], topicIds: [], conceptIds: [], itemIds: [] };
  const inRemoved = new Set<string>();
  for (const chapter of chapters) {
    const chapterItems = chapter.topics.flatMap((t) => t.concepts.flatMap((k) => byConcept.get(k.id) ?? []));
    if (covered(chapterItems)) {
      result.chapterIds.push(chapter.id);
      chapterItems.forEach((id) => inRemoved.add(id));
      continue;
    }
    for (const topic of chapter.topics) {
      const topicItems = topic.concepts.flatMap((k) => byConcept.get(k.id) ?? []);
      if (covered(topicItems)) {
        result.topicIds.push(topic.id);
        topicItems.forEach((id) => inRemoved.add(id));
        continue;
      }
      for (const concept of topic.concepts) {
        const conceptItems = byConcept.get(concept.id) ?? [];
        if (covered(conceptItems)) {
          result.conceptIds.push(concept.id);
          conceptItems.forEach((id) => inRemoved.add(id));
        }
      }
    }
  }
  result.itemIds = [...selected].filter((id) => !inRemoved.has(id));
  return result;
}
