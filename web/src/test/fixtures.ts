// Real responses captured from the backend (AI_PROVIDER=mock), shared with the iOS contract
// tests: the web client is exercised against what the API actually returns.
import raw from "./fixtures.json";
import type { Schemas } from "../api/client";

type F = typeof raw;
export const fixtures = raw as unknown as {
  [K in keyof F]: F[K];
} & {
  session: Schemas["SessionRead"];
  card_learn: Schemas["SessionCard"];
  card_done: Schemas["SessionCard"];
  card_pending: Schemas["SessionCard"];
  answer_result: Schemas["AnswerResult"];
  answer_failed: Schemas["AnswerResult"];
  override: Schemas["AnswerResult"];
  concept: Schemas["ConceptRead"];
  concept_activated: Schemas["ConceptRead"];
  learning_items: Schemas["LearningItemRead"][];
  proposal_generating: Schemas["CurriculumProposalRead"];
  proposal_ready: Schemas["CurriculumProposalRead"];
  progress: Schemas["CourseProgress"];
  home: Schemas["HomeSummary"];
  outline: Schemas["ChapterOutline"][];
  chunk: Schemas["ChunkRead"];
};
