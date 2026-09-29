import type { Schemas } from "../../api/client";

// The editable copy of an AI curriculum proposal (docs/PROJECT_SPEC.md §20). Every edit is local;
// the result is sent in one `apply` call whose body the backend validates (titles, and that
// source chunks belong to the Course). Nothing here invents sources: a concept keeps exactly the
// passages the AI tied it to, merged concepts keep the union, added concepts have none.

export interface DraftConcept {
  key: string;
  title: string;
  description: string;
  existingConceptId: string | null;
  sources: Schemas["ProposalSource"][];
}

export interface DraftTopic {
  key: string;
  title: string;
  description: string;
  existingTopicId: string | null;
  concepts: DraftConcept[];
}

export interface DraftChapter {
  key: string;
  title: string;
  description: string;
  topics: DraftTopic[];
}

let counter = 0;
const newKey = () => `k${++counter}`;

function draftTopic(topic: Schemas["ProposalTopic"]): DraftTopic {
  return {
    key: newKey(),
    title: topic.title,
    description: topic.description,
    existingTopicId: topic.existing_topic_id ?? null,
    concepts: topic.concepts.map((c) => ({
      key: newKey(),
      title: c.title,
      description: c.description,
      existingConceptId: c.existing_concept_id ?? null,
      sources: c.sources,
    })),
  };
}

/** Chapter-scope proposals edit topics; Course-scope ones edit chapters of topics. */
export function draftFrom(proposal: Schemas["CurriculumProposalRead"]): {
  chapters: DraftChapter[] | null;
  topics: DraftTopic[];
} {
  if (proposal.chapter_id) {
    return { chapters: null, topics: (proposal.topics ?? []).map(draftTopic) };
  }
  return {
    chapters: (proposal.chapters ?? []).map((ch) => ({
      key: newKey(),
      title: ch.title,
      description: ch.description,
      topics: ch.topics.map(draftTopic),
    })),
    topics: [],
  };
}

export function blankConcept(): DraftConcept {
  return { key: newKey(), title: "", description: "", existingConceptId: null, sources: [] };
}

export function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list;
  const copy = [...list];
  const [item] = copy.splice(from, 1);
  if (item !== undefined) copy.splice(to, 0, item);
  return copy;
}

/** Merges concept `index` with the next one: first title, both descriptions, union of sources. */
export function mergeWithNext(concepts: DraftConcept[], index: number): DraftConcept[] {
  const first = concepts[index];
  const second = concepts[index + 1];
  if (!first || !second) return concepts;
  const seen = new Set(first.sources.map((s) => s.chunk_id));
  const merged: DraftConcept = {
    ...first,
    description: [first.description, second.description].filter(Boolean).join("\n"),
    sources: [...first.sources, ...second.sources.filter((s) => !seen.has(s.chunk_id))],
  };
  return [...concepts.slice(0, index), merged, ...concepts.slice(index + 2)];
}

/** Moves a concept to another topic (appended at its end). */
export function moveConcept(topics: DraftTopic[], conceptKey: string, toTopicKey: string): DraftTopic[] {
  const concept = topics.flatMap((t) => t.concepts).find((c) => c.key === conceptKey);
  if (!concept) return topics;
  return topics.map((t) => {
    const without = t.concepts.filter((c) => c.key !== conceptKey);
    return t.key === toTopicKey ? { ...t, concepts: [...without, concept] } : { ...t, concepts: without };
  });
}

const blank = (text: string) => text.trim().length === 0;

export function hasBlankTitles(chapters: DraftChapter[] | null, topics: DraftTopic[]): boolean {
  const allTopics = chapters ? chapters.flatMap((c) => c.topics) : topics;
  return (
    (chapters?.some((c) => blank(c.title)) ?? false) ||
    allTopics.some((t) => blank(t.title) || t.concepts.some((c) => blank(c.title)))
  );
}

function applyTopic(topic: DraftTopic): Schemas["ApplyTopic"] {
  return {
    title: topic.title.trim(),
    description: topic.description,
    existing_topic_id: topic.existingTopicId,
    concepts: topic.concepts.map((c) => ({
      title: c.title.trim(),
      description: c.description,
      existing_concept_id: c.existingConceptId,
      source_chunk_ids: c.sources.map((s) => s.chunk_id),
    })),
  };
}

export function applyBody(chapters: DraftChapter[] | null, topics: DraftTopic[]): Schemas["CurriculumApply"] {
  if (chapters) {
    return {
      chapters: chapters.map((ch) => ({
        title: ch.title.trim(),
        description: ch.description,
        topics: ch.topics.map(applyTopic),
      })),
      topics: null,
    };
  }
  return { chapters: null, topics: topics.map(applyTopic) };
}
