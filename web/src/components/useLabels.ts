import { useMemo } from "react";
import type { Schemas } from "../api/client";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/messages/en";

const STUDY_STATES = ["NOT_STUDIED", "STUDIED", "ACTIVE", "PAUSED", "COMPLETED"] as const;
const MEMORY_STATES = ["NEW", "LEARNING", "REVIEW", "RELEARNING", "MASTERED"] as const;
const OUTCOMES = ["AGAIN", "HARD", "GOOD", "EASY"] as const;
const CLASSIFICATIONS = ["CORRECT", "PARTIALLY_CORRECT", "MISCONCEPTION", "WRONG", "UNCERTAIN"] as const;
const ROLES = ["CORE_TRAINABLE", "SUPPORTING_TRAINABLE", "COMMON_TRAP", "INFORMATIONAL", "REFERENCE", "OPTIONAL_EXTENSION"] as const;
const CATEGORIES = ["law", "economics_business", "accounting_finance", "medicine_health", "sciences", "mathematics", "engineering", "computer_science", "languages", "humanities", "arts", "professional_exams", "other"] as const;
const LEVELS = ["all", "beginner", "intermediate", "advanced"] as const;
const SIZES = ["small", "medium", "large"] as const;
const SORTS = ["popular", "newest", "largest"] as const;

/**
 * The names of the server's values (study state, memory state, grades, roles, categories...) in
 * the interface language. The server decides the values; this only names them.
 */
export function useLabels() {
  const { t } = useI18n();
  return useMemo(() => {
    const names = <K extends string>(keys: readonly K[], prefix: string) =>
      Object.fromEntries(keys.map((key) => [key, t(`${prefix}.${key}` as MessageKey)])) as Record<K, string>;
    const pageLabel = (page: number | null | undefined, pageEnd: number | null | undefined, short = false): string | null => {
      if (page === null || page === undefined) return null;
      if (pageEnd !== null && pageEnd !== undefined && pageEnd !== page) {
        return t(short ? "label.pagesShort" : "label.pages", { a: page, b: pageEnd });
      }
      return t(short ? "label.pageShort" : "label.page", { n: page });
    };
    return {
      studyStateLabel: names<Schemas["StudyState"]>(STUDY_STATES, "studyState"),
      memoryStateLabel: names<Schemas["MemoryState"]>(MEMORY_STATES, "memoryState"),
      outcomeLabel: names<Schemas["ReviewOutcome"]>(OUTCOMES, "outcome"),
      outcomeExplanation: names<Schemas["ReviewOutcome"]>(OUTCOMES, "outcomeHelp"),
      classificationLabel: names<Schemas["EvaluationClassification"]>(CLASSIFICATIONS, "classification"),
      roleLabel: names<Schemas["LearningItemRole"]>(ROLES, "role"),
      categoryLabel: names<Schemas["Category"]>(CATEGORIES, "category"),
      levelLabel: names<Schemas["Level"]>(LEVELS, "level"),
      sizeLabel: names<"small" | "medium" | "large">(SIZES, "size"),
      sortLabel: names<Schemas["ListingSort"]>(SORTS, "sort"),
      priorityLabel: { 1: t("priority.1"), 2: t("priority.2"), 3: t("priority.3") } as Record<number, string>,
      languageName: (code: string) => (code === "it" || code === "en" ? t(`lang.${code}`) : code),
      pageLabel,
      sourceSummary: (source: Schemas["ProposalSource"]) => {
        const parts = [source.document_name];
        const pages = pageLabel(source.page_number, source.page_end, true);
        if (pages) parts.push(pages);
        if (source.section) parts.push(source.section);
        return parts.join(" · ");
      },
      priceLabel: (listing: { price_cents: number; currency: string }) =>
        listing.price_cents === 0 ? t("price.free") : new Intl.NumberFormat(undefined, { style: "currency", currency: listing.currency }).format(listing.price_cents / 100),
      /** "1 question" / "5 questions" from `base.one` / `base.other`. */
      count: (base: string, n: number) => t(`${base}.${n === 1 ? "one" : "other"}` as MessageKey, { n }),
    };
  }, [t]);
}
