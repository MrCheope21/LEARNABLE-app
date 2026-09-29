import type { Concept } from "./geometry.ts";

// The one place that decides which identity the app shows. Concept 5 (the wordmark with the
// recall-loop "a") is the provisional default; concept 3 ("pages in motion") is the prepared
// alternative. Switch here, then run `node scripts/export-brand.ts` to refresh the favicon.
export const ACTIVE_CONCEPT: Concept = "concept5";
