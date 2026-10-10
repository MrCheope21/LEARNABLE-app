import type { Schemas } from "../api/client";

// Plain values and formats. The names of the server's values (study state, grades, roles,
// categories...) live in the interface language: see useLabels().

export const userGrades: Schemas["ReviewOutcome"][] = ["AGAIN", "HARD", "GOOD", "EASY"];

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const SECONDS_PER_REVIEW = 45;

/** Rough study time for a number of scheduled reviews, at least a minute. */
export function studyMinutes(items: number): number {
  return items <= 0 ? 0 : Math.max(1, Math.round((items * SECONDS_PER_REVIEW) / 60));
}
