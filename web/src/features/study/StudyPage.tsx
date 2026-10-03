import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { concepts, courses, dashboard } from "../../api/endpoints";
import { dashboardKey, XpIcon } from "../../app/AppShell";
import { BrandLogo } from "../../brand/BrandLogo";
import { ErrorBanner } from "../../components/QueryState";
import {
  dateTime,
  outcomeExplanation,
  outcomeLabel,
  studyMinutes,
  userGrades,
} from "../../components/labels";
import { courseProgressKey, weakSpotsKey } from "../curriculum/CourseLayout";
import { homeKey } from "../home/HomePage";
import { SourceLink, SourcePanel, type SourceRef } from "../source/SourcePanel";
import { DisputeForm } from "./DisputeForm";
import { recognitionLanguage, useDictation } from "./useDictation";
import { EvaluationView } from "./EvaluationView";
import { useStudySession, type AnswerView, type Card } from "./useStudySession";

const intentTitle: Record<Schemas["SessionIntent"], string> = {
  LEARN: "Learn",
  SCHEDULED_REVIEW: "Review",
  PRACTICE: "Practice",
  EXAM: "Exam",
  CONSOLIDATION: "Consolidation",
};

/** Builds the session request from the URL: /study/:courseId?intent=…&mode=…&concepts=a,b */
export function sessionRequestFrom(params: URLSearchParams): Schemas["SessionCreate"] {
  const intent = (params.get("intent") ?? "SCHEDULED_REVIEW") as Schemas["SessionIntent"];
  const mode = params.get("mode") as Schemas["SelectionMode"] | null;
  const concepts = params.get("concepts");
  return {
    intent,
    selection_mode: mode,
    concept_ids: concepts ? concepts.split(",").filter(Boolean) : null,
    limit: 20,
    update_schedule: false,
  };
}

export function studyLink(
  courseId: string,
  intent: Schemas["SessionIntent"],
  options: { mode?: Schemas["SelectionMode"]; conceptIds?: string[] } = {},
): string {
  const params = new URLSearchParams({ intent });
  if (options.mode) params.set("mode", options.mode);
  if (options.conceptIds?.length) params.set("concepts", options.conceptIds.join(","));
  return `/study/${courseId}?${params.toString()}`;
}

/**
 * A focused study session (docs/PROJECT_SPEC.md §65): one question at a time, then the backend's
 * evaluation, with the source material beside it. Keyboard: Ctrl/⌘+Enter submits, Enter
 * continues, 1–4 grade when a grade is needed.
 */
export function StudyPage() {
  const { courseId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  // Stable for the page's life: a new session must not start on every render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const request = useMemo(() => sessionRequestFrom(searchParams), []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const resumeId = useMemo(() => searchParams.get("session"), []);
  const s = useStudySession(courseId, request, resumeId);
  const [source, setSource] = useState<SourceRef | null>(null);
  const queryClient = useQueryClient();
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const intent = s.session?.intent ?? request.intent;
  const consolidating = intent === "CONSOLIDATION";

  // Streak, goal, XP and due counts change with every graded answer: keep them fresh.
  const graded = Object.keys(s.outcomes).length;
  useEffect(() => {
    if (graded === 0) return;
    void queryClient.invalidateQueries({ queryKey: dashboardKey });
    void queryClient.invalidateQueries({ queryKey: homeKey });
    void queryClient.invalidateQueries({ queryKey: courseProgressKey(courseId) });
    void queryClient.invalidateQueries({ queryKey: weakSpotsKey(courseId) });
  }, [graded, queryClient, courseId]);

  const close = async () => {
    // A consolidation batch stays open so it can be resumed exactly where it stopped.
    if (!consolidating) await s.end();
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    navigate(`/courses/${courseId}`);
  };

  const card = "card" in s.phase ? s.phase.card : null;
  // While a result is shown the server has already moved on: count the slot just answered.
  const position =
    s.session && s.session.total > 0
      ? Math.max(1, Math.min(s.session.position + (s.phase.kind === "result" ? 0 : 1), s.session.total))
      : null;

  return (
    <div className="study">
      <header className="study-header">
        <div>
          <Link to="/" className="home-link" aria-label="LEARNABLE home">
            <BrandLogo form="mark" height={28} />
          </Link>
          <ol className="breadcrumb" aria-label="Breadcrumb">
            <li>
              <Link to={`/courses/${courseId}`}>{course.data?.title ?? "Course"}</Link>
            </li>
            {card && (
              <li>
                <Link to={`/courses/${courseId}/concepts/${card.concept_id}`}>{card.concept_title}</Link>
              </li>
            )}
          </ol>
          <span className="eyebrow">{intentTitle[intent]}</span>
          {card?.round && card.rounds_total ? (
            <span className="round-badge">
              Round {card.round} of {card.rounds_total}
            </span>
          ) : null}
          {position !== null && s.session && (
            <span className="counter" aria-label="Progress in this session">
              {position} of {s.session.total}
            </span>
          )}
          {s.session && s.session.xp_earned > 0 && (
            <span className="xp-chip" aria-label={`${s.session.xp_earned} XP this session`}>
              <XpIcon /> {s.session.xp_earned} XP
            </span>
          )}
          {s.session && !s.session.affects_schedule && (
            <span className="pill">Practice: your schedule isn't changed</span>
          )}
        </div>
        <button type="button" onClick={() => void close()}>
          {consolidating ? "Leave (resume later)" : "End session"}
        </button>
      </header>

      <div className={source ? "study-body with-panel" : "study-body"}>
        <main className="study-main">
          <ErrorBanner error={s.error} onDismiss={s.clearError} />
          <PhaseView
            s={s}
            openSource={setSource}
            courseId={courseId}
            language={recognitionLanguage(course.data?.language)}
            onClose={() => void close()}
          />
        </main>
        {source && <SourcePanel source={source} onClose={() => setSource(null)} />}
      </div>
    </div>
  );
}

type Session = ReturnType<typeof useStudySession>;

function PhaseView({
  s,
  openSource,
  courseId,
  language,
  onClose,
}: {
  s: Session;
  openSource: (source: SourceRef) => void;
  courseId: string;
  language: string;
  onClose: () => void;
}) {
  const phase = s.phase;
  switch (phase.kind) {
    case "starting":
      return (
        <div className="state" role="status">
          Preparing your session…
        </div>
      );
    case "introduction":
      return <Introduction card={phase.card} onReady={s.beginRecall} openSource={openSource} />;
    case "answering":
    case "submitting":
      return <Answer card={phase.card} s={s} submitting={phase.kind === "submitting"} language={language} />;
    case "result":
      return <Result card={phase.card} result={phase.result} s={s} openSource={openSource} />;
    case "finished":
      return <Finished s={s} onClose={onClose} />;
    case "empty":
      return (
        <div className="state">
          <h2>Nothing to study right now</h2>
          <p>Nothing qualifies for this session. Activate a concept to add new material, or come back when reviews are due.</p>
          <Link className="button primary" to={`/courses/${courseId}`}>
            Back to the course
          </Link>
        </div>
      );
    case "failed":
      return (
        <div className="state error-state" role="alert">
          <p>{phase.message}</p>
          <button type="button" onClick={() => void (s.session ? s.loadNext() : s.start())}>
            Try again
          </button>
        </div>
      );
  }
}

function Introduction({
  card,
  onReady,
  openSource,
}: {
  card: Card;
  onReady: () => void;
  openSource: (source: SourceRef) => void;
}) {
  const intro = card.introduction;
  const ready = useRef<HTMLButtonElement>(null);
  useEffect(() => ready.current?.focus(), []);
  if (!intro) return null;
  return (
    <article className="card">
      <span className="eyebrow">New material</span>
      <h2>{intro.title}</h2>
      {intro.objective && <p className="hint">{intro.objective}</p>}
      <p className="reading">{intro.expected_knowledge}</p>
      {intro.essential_points.length > 0 && <Points title="Key points" points={intro.essential_points} />}
      <Sources sources={intro.sources} openSource={openSource} />
      <button ref={ready} type="button" className="primary large" onClick={onReady}>
        I'm ready: test me <kbd>Enter</kbd>
      </button>
    </article>
  );
}

function Answer({ card, s, submitting, language }: { card: Card; s: Session; submitting: boolean; language: string }) {
  const editor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => editor.current?.focus(), [card.question.id]);
  const dictation = useDictation(language, s.appendDictation);
  const stopDictation = dictation.stop;
  useEffect(() => {
    if (submitting) stopDictation();
  }, [submitting, stopDictation]);

  const onKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void s.submit();
    }
  };

  return (
    <article className="card">
      <span className="eyebrow">{card.concept_title}</span>
      <h2 className="question">{card.question.text}</h2>
      <PotentialXp card={card} />
      <HintBox card={card} s={s} disabled={submitting} />
      <label className="sr-only" htmlFor="answer">
        Your answer
      </label>
      <textarea
        id="answer"
        ref={editor}
        value={s.draft}
        onChange={(e) => s.setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={submitting}
        rows={9}
        placeholder="Answer in your own words…"
      />
      {dictation.listening && dictation.interim && (
        <p className="interim" aria-live="polite">
          {dictation.interim}
        </p>
      )}
      {dictation.error && (
        <p className="banner warning" role="status">
          {dictation.error}
        </p>
      )}
      <div className="actions">
        {dictation.supported && (
          <button
            type="button"
            className={dictation.listening ? "mic listening" : "mic"}
            aria-pressed={dictation.listening}
            disabled={submitting}
            onClick={dictation.listening ? dictation.stop : dictation.start}
          >
            {dictation.listening ? "Stop listening" : "Speak your answer"}
          </button>
        )}
        <button type="button" className="primary" disabled={!s.canSubmit || submitting} onClick={() => void s.submit()}>
          {submitting ? "Evaluating…" : "Submit"} <kbd>Ctrl/⌘ Enter</kbd>
        </button>
        <button type="button" className="link" disabled={submitting || s.working} onClick={() => void s.skip()}>
          Skip this question
        </button>
      </div>
      <p className="hint">
        {dictation.supported
          ? "Dictation is transcribed by your browser, which may send the audio to its speech service. Only the text is kept; edit it before you submit."
          : "Voice answers need Chrome, Edge or Safari. You can type your answer here."}
      </p>
    </article>
  );
}

function Result({
  card,
  result,
  s,
  openSource,
}: {
  card: Card;
  result: AnswerView;
  s: Session;
  openSource: (source: SourceRef) => void;
}) {
  const [disputing, setDisputing] = useState(false);
  const gradeMode = result.needs_self_grade || disputing;
  const continueButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!result.needs_self_grade) continueButton.current?.focus();
  }, [result.answer_id, result.needs_self_grade]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) return;
      if (gradeMode && ["1", "2", "3", "4"].includes(event.key)) {
        const grade = userGrades[Number(event.key) - 1];
        if (grade) {
          event.preventDefault();
          setDisputing(false);
          void s.override(grade);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [gradeMode, s]);

  const evaluation = result.evaluation;
  const outcome = result.final_outcome;
  const evaluationFailed = evaluation && evaluation.status !== "COMPLETED";
  const showDispute = disputing && evaluation?.status === "COMPLETED";
  const gradeTitle = result.needs_self_grade
    ? "How well did you know it?"
    : showDispute
      ? "Or grade it yourself"
      : "Your grade";

  return (
    <article className="card result">
      <span className="eyebrow">{card.concept_title}</span>
      <h2 className="question">{card.question.text}</h2>
      <section className="your-answer" aria-label="Your answer">
        <h3>Your answer</h3>
        <p>{result.text}</p>
      </section>

      <header className="outcome" aria-live="polite">
        {outcome ? (
          <>
            <span className={`outcome-badge outcome-${outcome.toLowerCase()}`}>{outcomeLabel[outcome]}</span>
            {result.override_outcome && <span className="hint">Graded by you</span>}
          </>
        ) : (
          <span className="outcome-badge">Needs your grade</span>
        )}
      </header>

      <Award result={result} />

      {evaluation && (
        <section className="evaluation" aria-label="First evaluation">
          {result.second_opinion && <h3>First evaluation</h3>}
          <EvaluationView evaluation={evaluation} />
        </section>
      )}
      {result.second_opinion && (
        <section className="evaluation second-opinion" aria-label="Second opinion">
          <h3>Second opinion</h3>
          <p className="hint">After your objection: “{result.second_opinion.user_argument}”</p>
          <EvaluationView evaluation={result.second_opinion} />
        </section>
      )}

      <details className="reference" open={!outcome || outcome === "AGAIN"}>
        <summary>Reference answer and sources</summary>
        <p className="reading">{result.reference.expected_knowledge}</p>
        {result.reference.essential_points.length > 0 && (
          <Points title="Key points" points={result.reference.essential_points} />
        )}
        <Sources sources={result.reference.sources} openSource={openSource} />
      </details>

      <ScheduleNote result={result} />

      {gradeMode ? (
        <section className="grades" aria-label="Your grade">
          {showDispute && <DisputeForm working={s.working} onAsk={s.dispute} />}
          <h3>{gradeTitle}</h3>
          <div className="grade-row">
            {userGrades.map((grade, index) => (
              <button
                key={grade}
                type="button"
                className={`grade grade-${grade.toLowerCase()}`}
                disabled={s.working || grade === result.final_outcome}
                onClick={() => {
                  setDisputing(false);
                  void s.override(grade);
                }}
              >
                <strong>{outcomeLabel[grade]}</strong>
                <span>{outcomeExplanation[grade]}</span>
                <kbd>{index + 1}</kbd>
              </button>
            ))}
          </div>
          <div className="actions">
            {evaluationFailed && (
              <button type="button" disabled={s.working} onClick={() => void s.retryEvaluation()}>
                Try the evaluation again
              </button>
            )}
            {disputing && (
              <button type="button" className="link" onClick={() => setDisputing(false)}>
                Cancel
              </button>
            )}
            {result.needs_self_grade && (
              <button type="button" className="link" disabled={s.working} onClick={() => void s.skip()}>
                Skip for now
              </button>
            )}
          </div>
        </section>
      ) : (
        <div className="actions">
          <button
            ref={continueButton}
            type="button"
            className="primary"
            disabled={s.working}
            onClick={() => void s.loadNext()}
          >
            Continue <kbd>Enter</kbd>
          </button>
          <button type="button" className="link" disabled={s.working} onClick={() => setDisputing(true)}>
            Disagree with the grade?
          </button>
        </div>
      )}
    </article>
  );
}

function ScheduleNote({ result }: { result: AnswerView }) {
  const schedule = result.schedule;
  if (schedule) {
    if (schedule.next_state === "NEW") {
      return <p className="hint">Not memorized yet: you'll see it again in this session.</p>;
    }
    return (
      <p className="hint">
        Level {schedule.previous_level} → {schedule.next_level}. Next review: {dateTime(schedule.next_due_at)}
      </p>
    );
  }
  if (result.intent === "PRACTICE" && result.final_outcome) {
    return <p className="hint">Practice doesn't change your review schedule.</p>;
  }
  return null;
}

function Finished({ s, onClose }: { s: Session; onClose: () => void }) {
  const [now] = useState(() => Date.now());
  const dueNow = useQuery({
    queryKey: dashboardKey,
    queryFn: dashboard.get,
    select: (d) => d.planner.horizons.find((h) => h.key === "now")?.items ?? 0,
  });
  if (s.session?.intent === "CONSOLIDATION") return <ConsolidationDone s={s} onClose={onClose} />;
  const counts = userGrades
    .map((grade) => [grade, Object.values(s.outcomes).filter((o) => o === grade).length] as const)
    .filter(([, count]) => count > 0);
  const answered = Object.keys(s.outcomes).length;
  const wentWell = Object.values(s.outcomes).filter((o) => o === "GOOD" || o === "EASY").length;
  const started = s.session ? Date.parse(s.session.started_at) : now;
  const minutes = Math.max(1, Math.round((now - started) / 60_000));
  return (
    <div className="state">
      <h2>Session complete</h2>
      {s.session && s.session.xp_earned > 0 && (
        <p className="xp-chip">
          <XpIcon /> +{s.session.xp_earned} XP this session
        </p>
      )}
      <p>
        {answered} {answered === 1 ? "answer" : "answers"} in about {minutes} min.
        {answered > 0 && ` ${wentWell} went well.`}
      </p>
      <ul className="inline-list">
        {counts.map(([grade, count]) => (
          <li key={grade}>
            {outcomeLabel[grade]}: {count}
          </li>
        ))}
      </ul>
      {answered > 0 && (
        <p className="hint">
          {wentWell * 10 >= answered * 7
            ? "Steady work: this is settling in."
            : "The ones that went badly come back soon, which is how they stick."}
        </p>
      )}
      {dueNow.data !== undefined && (
        <p className="hint">
          {dueNow.data > 0
            ? `Still due now: ${dueNow.data} (about ${studyMinutes(dueNow.data)} min).`
            : "Nothing else is due right now."}
        </p>
      )}
      <button type="button" className="primary" onClick={onClose}>
        Done
      </button>
    </div>
  );
}

function Points({ title, points }: { title: string; points: string[] }) {
  return (
    <section className="points">
      <h3>{title}</h3>
      <ul>
        {points.map((point, index) => (
          <li key={index}>{point}</li>
        ))}
      </ul>
    </section>
  );
}

function Sources({ sources, openSource }: { sources: SourceRef[]; openSource: (source: SourceRef) => void }) {
  if (sources.length === 0) return null;
  return (
    <section className="sources">
      <h3>Sources</h3>
      <ul>
        {sources.map((source) => (
          <li key={source.chunk_id}>
            <SourceLink source={source} onOpen={openSource} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function PotentialXp({ card }: { card: Card }) {
  const potential = card.potential_xp;
  if (!potential) return null;
  if (!potential.eligible) {
    return <p className="potential">This answer doesn't earn XP (practice, or not due for review).</p>;
  }
  const revealed = card.hint?.revealed ?? false;
  return (
    <p className="potential">
      <span className="xp-chip">
        <XpIcon /> Correct answer: +{revealed ? potential.xp_with_hint : potential.xp} XP
      </span>
      {revealed && <span>(hint used: half XP)</span>}
    </p>
  );
}

/** "Show hint": the halving is stated before anything is revealed; the server records it. */
function HintBox({ card, s, disabled }: { card: Card; s: Session; disabled: boolean }) {
  const [confirming, setConfirming] = useState(false);
  const hint = card.hint;
  if (!hint) return null;
  if (hint.revealed) {
    return (
      <div className="hint-box" role="note" aria-label="Hint">
        <span className="eyebrow">Hint</span>
        <span className="hint-text">{hint.text}</span>
      </div>
    );
  }
  if (!hint.available) return <p className="hint">No hint for this question.</p>;
  if (!confirming) {
    return (
      <div>
        <button type="button" className="link" disabled={disabled} onClick={() => setConfirming(true)}>
          Show hint
        </button>
      </div>
    );
  }
  return (
    <div className="hint-box">
      <p>Using a hint halves the XP for this answer.</p>
      <div className="actions" style={{ marginTop: 0 }}>
        <button
          type="button"
          className="primary"
          disabled={disabled || s.working}
          onClick={() => {
            void s.revealHint();
            setConfirming(false);
          }}
        >
          Reveal hint
        </button>
        <button type="button" className="link" onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Award({ result }: { result: AnswerView }) {
  const xp = result.xp;
  if (!xp) return null;
  if (!xp.correct) {
    const selfGraded = result.override_outcome !== null && result.resolved_outcome === null;
    return (
      <p className="award award-pop" aria-live="polite">
        <span className="xp-chip">
          <XpIcon /> +0 XP
        </span>
        <span className="hint">
          {selfGraded
            ? "Answers you grade yourself don't earn correctness XP."
            : "Only fully correct answers earn XP. Your progress towards the next award is kept."}
        </span>
      </p>
    );
  }
  const parts = ["Correct", `+${xp.xp} XP`];
  if (xp.hint_used) parts.push("Hint used");
  return (
    <p className="award award-pop" aria-live="polite">
      <span className="xp-chip">
        <XpIcon /> {parts.join(" \u00b7 ")}
      </span>
      {xp.ordinal !== null && (
        <span className="hint">
          correct answer #{xp.ordinal} for this item{xp.hint_used ? `, half of ${xp.base_xp}` : ""}
        </span>
      )}
    </p>
  );
}

function ConsolidationDone({ s, onClose }: { s: Session; onClose: () => void }) {
  const results = Object.values(s.results);
  const rounds = results.filter((r) => r.final_outcome).length;
  const correct = results.filter((r) => r.xp?.correct).length;
  const conceptId = s.session?.concept_ids?.[0] ?? null;
  const courseId = s.session?.course_id ?? "";
  const plan = useQuery({
    queryKey: ["consolidation", conceptId],
    queryFn: () => concepts.consolidationPlan(conceptId ?? ""),
    enabled: conceptId !== null,
  });
  const waiting = plan.data?.new_items ?? 0;
  return (
    <div className="card" style={{ display: "grid", gap: "1rem" }}>
      <h2>Batch consolidated</h2>
      <dl className="summary-grid">
        <div>
          <dt>Correct answers</dt>
          <dd>
            {correct} / {rounds}
          </dd>
        </div>
        <div>
          <dt>XP this session</dt>
          <dd>+{s.session?.xp_earned ?? 0}</dd>
        </div>
        <div>
          <dt>What happens next</dt>
          <dd style={{ fontSize: "1rem", fontWeight: 500 }}>
            Items whose last round was right come back for review in about 4 hours; the others wait for the next batch.
          </dd>
        </div>
      </dl>
      <p className="hint">
        {waiting > 0
          ? `This batch is done, not the whole concept: ${waiting} more ${waiting === 1 ? "item is" : "items are"} waiting.`
          : "Every item in this concept that was waiting has had its three rounds."}
      </p>
      <div className="actions">
        {waiting > 0 && conceptId && (
          <Link className="button learn" to={`/courses/${courseId}/concepts/${conceptId}`}>
            Next batch
          </Link>
        )}
        <button type="button" className={waiting > 0 ? undefined : "primary"} onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  );
}
