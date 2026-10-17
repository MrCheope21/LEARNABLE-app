import type { ReactNode } from "react";
import type { Schemas } from "../../api/client";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

type Evaluation = Schemas["EvaluationRead"];

const DIMENSIONS = [
  ["correctness", "eval.correct"],
  ["completeness", "eval.complete"],
  ["conceptual_understanding", "eval.understanding"],
  ["precision", "eval.precise"],
] as const;

function rating(value: number): "Strong" | "Partial" | "Weak" {
  if (value >= 0.8) return "Strong";
  if (value >= 0.5) return "Partial";
  return "Weak";
}

/** The evaluator's four scores, one short row each, instead of a single grade. */
export function ScoreBreakdown({ evaluation }: { evaluation: Evaluation }) {
  const { t } = useI18n();
  const rows = DIMENSIONS.flatMap(([key, labelKey]) => {
    const value = evaluation[key];
    return value === null ? [] : [{ key, label: t(labelKey), value, grade: rating(value) }];
  });
  if (rows.length === 0) return null;
  return (
    <ul className="scores" aria-label={t("eval.scoreBreakdown")}>
      {rows.map(({ key, label, value, grade }) => (
        <li key={key}>
          <span className="score-label">{label}</span>
          <meter min={0} max={1} low={0.5} high={0.8} optimum={1} value={value} aria-label={`${label}: ${t(`eval.${grade}` as MessageKey)}`} />
          <span className={`score-rating ${TONE[grade]}`}>{t(`eval.${grade}` as MessageKey)}</span>
        </li>
      ))}
    </ul>
  );
}

const TONE = { Strong: "tone-good", Partial: "tone-warn", Weak: "tone-bad" } as const;

const CHECKS = [
  ["correct_points", "good", "✓", "eval.right"],
  ["missing_points", "warn", "✗", "eval.missing"],
  ["misconceptions", "bad", "!", "eval.misconception"],
  ["source_corrections", "info", "i", "eval.materialSays"],
] as const;

/** One line of a checklist: a toned mark, then the text. `word` is read out by screen readers. */
export function CheckRow({ tone, mark, word, children }: { tone: "good" | "warn" | "bad" | "info"; mark: string; word: string; children: ReactNode }) {
  return (
    <li className="check">
      <span className={`check-mark tone-${tone}`} aria-hidden="true">
        {mark}
      </span>
      <span className="sr-only">{word}: </span>
      <span>{children}</span>
    </li>
  );
}

/** What was right, what was missing, what was a misconception: one checklist. */
export function PointChecklist({ evaluation }: { evaluation: Evaluation }) {
  const { t } = useI18n();
  const rows = CHECKS.flatMap(([key, tone, mark, word]) =>
    evaluation[key].map((text) => ({ tone, mark, word: t(word), text })),
  );
  if (rows.length === 0) return null;
  return (
    <ul className="checklist" aria-label={t("eval.covered")}>
      {rows.map((row, index) => (
        <CheckRow key={index} tone={row.tone} mark={row.mark} word={row.word}>
          {row.text}
        </CheckRow>
      ))}
    </ul>
  );
}

/** One evaluation: its verdict, feedback, scores and checklist. Used for both opinions. */
export function EvaluationView({ evaluation }: { evaluation: Evaluation }) {
  const { t } = useI18n();
  const { classificationLabel } = useLabels();
  if (evaluation.status !== "COMPLETED") {
    return (
      <p className="banner warning" role="status">
        {evaluation.error_message ?? t("eval.failed")}
      </p>
    );
  }
  return (
    <div className="evaluation-body">
      {evaluation.ai_provider === "mock" && <TestAiNotice />}
      {evaluation.classification && (
        <span className="hint">{t("eval.aiEvaluation", { verdict: classificationLabel[evaluation.classification] })}</span>
      )}
      {evaluation.feedback && <p>{evaluation.feedback}</p>}
      {evaluation.context_sufficient === false && (
        <p className="banner warning">{t("eval.insufficient")}</p>
      )}
      <ScoreBreakdown evaluation={evaluation} />
      <PointChecklist evaluation={evaluation} />
    </div>
  );
}

/** The server runs the offline test AI: its grades only compare words, so say so plainly. */
export function TestAiNotice() {
  const { t } = useI18n();
  return (
    <p className="banner warning test-ai" role="note">
      <strong>{t("eval.testAiTitle")}</strong> {t("eval.testAiBody")}
    </p>
  );
}
