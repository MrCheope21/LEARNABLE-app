import type { Schemas } from "../api/client";

// User-facing names for server values. The server decides them; this only names them.

export const studyStateLabel: Record<Schemas["StudyState"], string> = {
  NOT_STUDIED: "Not studied",
  STUDIED: "Studied",
  ACTIVE: "Active",
  PAUSED: "Paused",
  COMPLETED: "Completed",
};

export const memoryStateLabel: Record<Schemas["MemoryState"], string> = {
  NEW: "New",
  LEARNING: "Learning",
  REVIEW: "In review",
  RELEARNING: "Relearning",
  MASTERED: "Mastered",
};

export const outcomeLabel: Record<Schemas["ReviewOutcome"], string> = {
  AGAIN: "Again",
  HARD: "Hard",
  GOOD: "Good",
  EASY: "Easy",
};

export const outcomeExplanation: Record<Schemas["ReviewOutcome"], string> = {
  AGAIN: "I didn't know it",
  HARD: "I knew it, with difficulty",
  GOOD: "I knew it",
  EASY: "I knew it easily",
};

export const userGrades: Schemas["ReviewOutcome"][] = ["AGAIN", "HARD", "GOOD", "EASY"];

export const classificationLabel: Record<Schemas["EvaluationClassification"], string> = {
  CORRECT: "Correct",
  PARTIALLY_CORRECT: "Partly correct",
  MISCONCEPTION: "Misconception",
  WRONG: "Not correct",
  UNCERTAIN: "Uncertain",
};

export const roleLabel: Record<Schemas["LearningItemRole"], string> = {
  CORE_TRAINABLE: "Core",
  SUPPORTING_TRAINABLE: "Supporting",
  COMMON_TRAP: "Common trap",
  INFORMATIONAL: "Informational",
  REFERENCE: "Reference",
  OPTIONAL_EXTENSION: "Optional",
};

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "Page 8" / "Pages 8–9" (or "p. 8" / "pp. 8–9" when short); null for formats without pages. */
export function pageLabel(
  page: number | null | undefined,
  pageEnd: number | null | undefined,
  short = false,
): string | null {
  if (page === null || page === undefined) return null;
  if (pageEnd !== null && pageEnd !== undefined && pageEnd !== page) {
    return `${short ? "pp." : "Pages"} ${page}–${pageEnd}`;
  }
  return `${short ? "p." : "Page"} ${page}`;
}

export function sourceSummary(source: Schemas["ProposalSource"]): string {
  const parts = [source.document_name];
  const pages = pageLabel(source.page_number, source.page_end, true);
  if (pages) parts.push(pages);
  if (source.section) parts.push(source.section);
  return parts.join(" · ");
}

const SECONDS_PER_REVIEW = 45;

/** Rough study time for a number of scheduled reviews, at least a minute. */
export function studyMinutes(items: number): number {
  return items <= 0 ? 0 : Math.max(1, Math.round((items * SECONDS_PER_REVIEW) / 60));
}
