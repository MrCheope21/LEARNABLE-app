import type { ReactNode } from "react";
import type { Schemas } from "../../api/client";
import { classificationLabel } from "../../components/labels";

type Evaluation = Schemas["EvaluationRead"];

const DIMENSIONS = [
  ["correctness", "Correct"],
  ["completeness", "Complete"],
  ["conceptual_understanding", "Understanding"],
  ["precision", "Precise"],
] as const;

function rating(value: number): "Strong" | "Partial" | "Weak" {
  if (value >= 0.8) return "Strong";
  if (value >= 0.5) return "Partial";
  return "Weak";
}

/** The evaluator's four scores, one short row each, instead of a single grade. */
export function ScoreBreakdown({ evaluation }: { evaluation: Evaluation }) {
  const rows = DIMENSIONS.flatMap(([key, label]) => {
    const value = evaluation[key];
    return value === null ? [] : [{ key, label, value, grade: rating(value) }];
  });
  if (rows.length === 0) return null;
  return (
    <ul className="scores" aria-label="Score breakdown">
      {rows.map(({ key, label, value, grade }) => (
        <li key={key}>
          <span className="score-label">{label}</span>
          <meter min={0} max={1} low={0.5} high={0.8} optimum={1} value={value} aria-label={`${label}: ${grade}`} />
          <span className={`score-rating ${TONE[grade]}`}>{grade}</span>
        </li>
      ))}
    </ul>
  );
}

const TONE = { Strong: "tone-good", Partial: "tone-warn", Weak: "tone-bad" } as const;

const CHECKS = [
  ["correct_points", "good", "✓", "Right"],
  ["missing_points", "warn", "✗", "Missing"],
  ["misconceptions", "bad", "!", "Misconception"],
  ["source_corrections", "info", "i", "The material says"],
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
  const rows = CHECKS.flatMap(([key, tone, mark, word]) =>
    evaluation[key].map((text) => ({ tone, mark, word, text })),
  );
  if (rows.length === 0) return null;
  return (
    <ul className="checklist" aria-label="What your answer covered">
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
  if (evaluation.status !== "COMPLETED") {
    return (
      <p className="banner warning" role="status">
        {evaluation.error_message ?? "The answer couldn't be evaluated."}
      </p>
    );
  }
  return (
    <div className="evaluation-body">
      {evaluation.classification && (
        <span className="hint">AI evaluation: {classificationLabel[evaluation.classification]}</span>
      )}
      {evaluation.feedback && <p>{evaluation.feedback}</p>}
      {evaluation.context_sufficient === false && (
        <p className="banner warning">The course material doesn't cover this well enough to grade it.</p>
      )}
      <ScoreBreakdown evaluation={evaluation} />
      <PointChecklist evaluation={evaluation} />
    </div>
  );
}
