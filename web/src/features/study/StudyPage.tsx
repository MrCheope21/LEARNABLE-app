import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { concepts, courses, dashboard, learningItems } from "../../api/endpoints";
import { dashboardKey, XpIcon } from "../../app/AppShell";
import { BrandLogo } from "../../brand/BrandLogo";
import { AuthImage } from "../../components/AuthImage";
import { DrawingPad } from "../../components/DrawingPad";
import { HelpTip } from "../../components/HelpTip";
import { ErrorBanner } from "../../components/QueryState";
import { dateTime, studyMinutes, userGrades } from "../../components/labels";
import { useLabels } from "../../components/useLabels";
import type { MessageKey } from "../../i18n/messages/en";
import { courseProgressKey, weakSpotsKey } from "../curriculum/CourseLayout";
import { homeKey } from "../home/HomePage";
import { SourceLink, SourcePanel, type SourceRef } from "../source/SourcePanel";
import { Icon } from "../../components/Icon";
import { QueuePanel } from "./QueuePanel";
import { ConceptPanel } from "./ConceptPanel";
import { useI18n } from "../../i18n";
import { DisputeForm } from "./DisputeForm";
import { recognitionLanguage, useDictation } from "./useDictation";
import { EvaluationView, GapLine } from "./EvaluationView";
import { useStudySession, type AnswerView, type Card } from "./useStudySession";

/** Builds the session request from the URL: /study/:courseId?intent=…&mode=…&concepts=a,b */
export function sessionRequestFrom(params: URLSearchParams): Schemas["SessionCreate"] {
  const intent = (params.get("intent") ?? "SCHEDULED_REVIEW") as Schemas["SessionIntent"];
  const mode = params.get("mode") as Schemas["SelectionMode"] | null;
  const concepts = params.get("concepts");
  const items = params.get("items");
  return {
    intent,
    selection_mode: items ? "SELECTED" : mode,
    concept_ids: concepts ? concepts.split(",").filter(Boolean) : null,
    learning_item_ids: items ? items.split(",").filter(Boolean) : null,
    // A chosen set is asked in full (up to 100); otherwise a session is 20 questions.
    limit: items ? Math.min(100, items.split(",").filter(Boolean).length || 20) : 20,
    update_schedule: false,
  };
}

export function studyLink(
  courseId: string,
  intent: Schemas["SessionIntent"],
  options: { mode?: Schemas["SelectionMode"]; conceptIds?: string[]; itemIds?: string[] } = {},
): string {
  const params = new URLSearchParams({ intent });
  if (options.mode) params.set("mode", options.mode);
  if (options.conceptIds?.length) params.set("concepts", options.conceptIds.join(","));
  if (options.itemIds?.length) params.set("items", options.itemIds.join(","));
  return `/study/${courseId}?${params.toString()}`;
}

/**
 * A focused study session (docs/PROJECT_SPEC.md §65): one question at a time, then the backend's
 * evaluation, with the source material beside it. Keyboard: Ctrl/⌘+Enter submits, Enter
 * continues, 1–4 grade when a grade is needed.
 */
export function StudyPage() {
  const { t } = useI18n();
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
  // One side panel at a time: a source passage, or the whole concept.
  const [conceptPanel, setConceptPanel] = useState<string | null>(null);
  const [queueOpen, setQueueOpen] = useState(false);
  const openSource = (ref: SourceRef) => {
    setConceptPanel(null);
    setQueueOpen(false);
    setSource(ref);
  };
  const openConcept = (conceptId: string) => {
    setSource(null);
    setQueueOpen(false);
    setConceptPanel(conceptId);
  };
  const openQueue = () => {
    setSource(null);
    setConceptPanel(null);
    setQueueOpen((open) => !open);
  };
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
        <Link to="/" className="home-link study-home" aria-label={t("nav.home")}>
          <BrandLogo form="mark" height={26} />
        </Link>
        <div className="study-where">
          <ol className="breadcrumb" aria-label={t("breadcrumb.aria")}>
            <li>
              <Link to={`/courses/${courseId}`}>{course.data?.title ?? t("course.fallback")}</Link>
            </li>
            {card && (
              <li>
                <Link to={`/courses/${courseId}/concepts/${card.concept_id}`}>{card.concept_title}</Link>
              </li>
            )}
          </ol>
          <div className="study-meta">
            <span className="eyebrow">{t(`study.intent.${intent}` as MessageKey)}</span>
            {card?.round && card.rounds_total ? (
              <span className="round-badge">{t("study.round", { n: card.round, total: card.rounds_total })}</span>
            ) : null}
            {s.session && !s.session.affects_schedule && <span className="pill">{t("study.ownReview")}</span>}
          </div>
        </div>
        <div className="study-tools">
          {s.session && s.session.xp_earned > 0 && (
            <span className="xp-chip" aria-label={t("study.xpSessionAria", { n: s.session.xp_earned })}>
              <XpIcon /> {t("community.xp", { n: s.session.xp_earned })}
            </span>
          )}
          {s.session && !consolidating && s.session.total > 1 && s.session.position < s.session.total && (
            <button type="button" className="queue-toggle" aria-pressed={queueOpen} onClick={openQueue}>
              <Icon name="list" size={16} /> <span>{t("queue.open", { n: s.session.total - s.session.position })}</span>
            </button>
          )}
          <button type="button" className="study-end" onClick={() => void close()}>
            {consolidating ? t("study.leaveResume") : t("study.end")}
          </button>
        </div>
        {position !== null && s.session && (
          <div className="study-progress">
            <span className="study-progress-track" aria-hidden="true">
              <span style={{ width: `${(Math.min(s.session.position, s.session.total) / s.session.total) * 100}%` }} />
            </span>
            <span className="counter" aria-label={t("study.progressAria")}>
              {t("study.progress", { n: position, total: s.session.total })}
            </span>
          </div>
        )}
      </header>

      <div className={source || conceptPanel || queueOpen ? "study-body with-panel" : "study-body"}>
        <main className="study-main">
          <ErrorBanner error={s.error} onDismiss={s.clearError} />
          <PhaseView
            s={s}
            openSource={openSource}
            openConcept={openConcept}
            courseId={courseId}
            language={recognitionLanguage(course.data?.language)}
            onClose={() => void close()}
          />
        </main>
        {source && <SourcePanel source={source} onClose={() => setSource(null)} />}
        {queueOpen && s.session && (
          <QueuePanel
            sessionId={s.session.id}
            working={s.working}
            onClose={() => setQueueOpen(false)}
            onPick={(itemId) => {
              setQueueOpen(false);
              void s.pick(itemId);
            }}
          />
        )}
        {conceptPanel && (
          <ConceptPanel
            courseId={courseId}
            conceptId={conceptPanel}
            onClose={() => setConceptPanel(null)}
            onNext={
              s.phase.kind === "result" && !s.phase.result.needs_self_grade && !s.phase.result.needs_repeat
                ? () => {
                    setConceptPanel(null);
                    void s.loadNext();
                  }
                : undefined
            }
            working={s.working}
          />
        )}
      </div>
    </div>
  );
}

type Session = ReturnType<typeof useStudySession>;

function PhaseView({
  s,
  openSource,
  openConcept,
  courseId,
  language,
  onClose,
}: {
  s: Session;
  openSource: (source: SourceRef) => void;
  openConcept: (conceptId: string) => void;
  courseId: string;
  language: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const phase = s.phase;
  switch (phase.kind) {
    case "starting":
      return (
        <div className="state" role="status">
          {t("study.preparing")}
        </div>
      );
    case "introduction":
      return <Introduction card={phase.card} onReady={s.beginRecall} openSource={openSource} />;
    case "answering":
    case "submitting":
      return (
        <Answer
          card={phase.card}
          s={s}
          submitting={phase.kind === "submitting"}
          language={language}
          openConcept={openConcept}
        />
      );
    case "result":
      return <Result card={phase.card} result={phase.result} s={s} openSource={openSource} openConcept={openConcept} />;
    case "finished":
      return <Finished s={s} onClose={onClose} />;
    case "empty":
      return (
        <div className="state">
          <h2>{t("study.empty.title")}</h2>
          <p>{t("study.empty.body")}</p>
          <Link className="button primary" to={`/courses/${courseId}`}>
            {t("study.empty.back")}
          </Link>
        </div>
      );
    case "failed":
      return (
        <div className="state error-state" role="alert">
          <p>{phase.message}</p>
          <button type="button" onClick={() => void (s.session ? s.loadNext() : s.start())}>
            {t("common.tryAgain")}
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
  const { t } = useI18n();
  const intro = card.introduction;
  const ready = useRef<HTMLButtonElement>(null);
  useEffect(() => ready.current?.focus(), []);
  if (!intro) return null;
  return (
    <article className="card">
      <span className="eyebrow">{t("study.newMaterial")}</span>
      <h2>{intro.title}</h2>
      {intro.objective && <p className="hint">{intro.objective}</p>}
      {intro.drawing && (
        <ReferenceDrawing itemId={card.learning_item_id} />
      )}
      <p className="reading">{intro.expected_knowledge}</p>
      {intro.essential_points.length > 0 && <Points title={t("study.keyPoints")} points={intro.essential_points} />}
      <Sources sources={intro.sources} openSource={openSource} />
      <button ref={ready} type="button" className="primary large" onClick={onReady}>
        {t("study.ready")} <kbd>Enter</kbd>
      </button>
    </article>
  );
}

function Answer({
  card,
  s,
  submitting,
  language,
  openConcept,
}: {
  card: Card;
  s: Session;
  submitting: boolean;
  language: string;
  openConcept: (conceptId: string) => void;
}) {
  const { t } = useI18n();
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

  const drawing = card.answer_format === "DRAWING";
  return (
    <article className="card answer-card">
      <div className="answer-top">
        <span className="eyebrow">{card.concept_title}</span>
        <span className="answer-top-right">
          <PotentialXp card={card} />
          <HelpTip text="help.study" topic={t("study.answering")} guide="answer" />
        </span>
      </div>
      <h2 className="question">{card.question.text}</h2>
      <HintBox card={card} s={s} disabled={submitting} revealedOnly />
      {drawing && (
        <>
          <p className="hint">{t("study.drawHint")}</p>
          <DrawingPad key={card.question.id} onChange={s.setDrawing} disabled={submitting} />
        </>
      )}
      <div className={dictation.listening ? "composer listening" : "composer"}>
        <label className={drawing ? "drawing-note-label" : "sr-only"} htmlFor="answer">
          {drawing ? t("study.note") : t("study.yourAnswer")}
        </label>
        <textarea
          id="answer"
          ref={editor}
          value={s.draft}
          onChange={(e) => s.setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={submitting}
          rows={drawing ? 2 : 7}
          className={drawing ? "drawing-note" : undefined}
          placeholder={drawing ? t("study.notePlaceholder") : t("study.answerPlaceholder")}
        />
        {dictation.listening && dictation.interim && (
          <p className="interim" aria-live="polite">
            {dictation.interim}
          </p>
        )}
        <div className="composer-bar">
          {dictation.supported && !drawing ? (
            <button
              type="button"
              className={dictation.listening ? "mic listening" : "mic"}
              aria-pressed={dictation.listening}
              disabled={submitting}
              title={t("study.dictationOn")}
              onClick={dictation.listening ? dictation.stop : dictation.start}
            >
              {dictation.listening ? t("study.stopListening") : t("study.speak")}
            </button>
          ) : (
            <span />
          )}
          <button type="button" className="primary composer-submit" disabled={!s.canSubmit || submitting} onClick={() => void s.submit()}>
            {submitting ? t("study.evaluating") : t("study.submit")} <kbd>Ctrl/⌘ Enter</kbd>
          </button>
        </div>
      </div>
      {dictation.error && (
        <p className="banner warning" role="status">
          {dictation.error}
        </p>
      )}
      <div className="answer-help" role="group" aria-label={t("study.helpGroup")}>
        <HintBox card={card} s={s} disabled={submitting} askOnly />
        <StudyConceptButton card={card} s={s} disabled={submitting} openConcept={openConcept} />
        <button type="button" className="help-chip" disabled={submitting || s.working} onClick={() => void s.skip()}>
          <Icon name="skip" size={18} /> {t("study.skip")}
        </button>
      </div>
      {!drawing && !dictation.supported && <p className="hint">{t("study.dictationOff")}</p>}
    </article>
  );
}

function Result({
  card,
  result,
  s,
  openSource,
  openConcept,
}: {
  card: Card;
  result: AnswerView;
  s: Session;
  openSource: (source: SourceRef) => void;
  openConcept: (conceptId: string) => void;
}) {
  const { t } = useI18n();
  const { outcomeLabel, outcomeExplanation } = useLabels();
  const [disputing, setDisputing] = useState(false);
  // Green on most scores: the student repeats the answer (it then counts as correct) instead of
  // grading; they can still choose to grade it themselves.
  const [selfGradingFor, setSelfGradingFor] = useState<string | null>(null);
  const selfGrading = selfGradingFor === result.answer_id;
  const repeating = result.needs_repeat && !selfGrading;
  const gradeMode = (result.needs_self_grade && !repeating) || disputing;
  // The repeated text belongs to one answer: a new answer starts empty.
  const [draft, setDraft] = useState<{ answerId: string; text: string }>({ answerId: "", text: "" });
  const again = draft.answerId === result.answer_id ? draft.text : "";
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
    ? t("study.gradeHow")
    : showDispute
      ? t("study.gradeYourself")
      : t("study.yourGrade");

  const tone = outcome ? outcome.toLowerCase() : repeating ? "good" : "pending";
  const shown = result.second_opinion ?? evaluation;
  return (
    <article className="card result">
      {/* 1. The verdict: what happened, what it earned, when it comes back. */}
      <header className={`verdict verdict-${tone}`}>
        <div className="outcome" aria-live="polite">
          {outcome ? (
            <>
              <span className={`outcome-badge outcome-${outcome.toLowerCase()}`}>{outcomeLabel[outcome]}</span>
              {result.override_outcome && <span className="hint">{t("study.gradedByYou")}</span>}
            </>
          ) : repeating ? (
            <span className="outcome-badge outcome-good">{t("study.repeat.badge")}</span>
          ) : (
            <span className="outcome-badge">{t("study.needsGrade")}</span>
          )}
        </div>
        <Award result={result} />
        <ScheduleNote result={result} />
        {shown && <GapLine evaluation={shown} />}
      </header>

      {/* 2. The question and what was answered. */}
      <div className="result-question">
        <span className="eyebrow">{card.concept_title}</span>
        <h2 className="question">{card.question.text}</h2>
      </div>
      {result.has_drawing ? (
        <section className="drawing-compare" aria-label={t("study.drawingCompare")}>
          <figure>
            <figcaption>{t("study.yourDrawing")}</figcaption>
            <AuthImage
              queryKey={["answer-drawing", result.answer_id]}
              load={() => learningItems.answerDrawing(result.answer_id)}
              alt={t("study.yourDrawing")}
              className="drawing-image"
            />
            {result.text && <p className="hint">{result.text}</p>}
          </figure>
          {result.reference.drawing && (
            <figure>
              <figcaption>{t("study.reference")}</figcaption>
              <ReferenceDrawing itemId={result.learning_item_id} />
            </figure>
          )}
        </section>
      ) : (
        <section className="your-answer" aria-label={t("study.yourAnswer")}>
          <h3>{t("study.yourAnswer")}</h3>
          <p>{result.text}</p>
        </section>
      )}

      {/* 3. Why: the evaluation. */}
      {shown && (
        <section className="evaluation" aria-label={t("study.evaluation")}>
          {result.second_opinion && (
            <div className="revision-banner" role="status">
              <strong>
                <Icon name="review" size={16} /> {t("study.revised")}
              </strong>
              {result.second_opinion.user_argument && <blockquote>“{result.second_opinion.user_argument}”</blockquote>}
            </div>
          )}
          <EvaluationView evaluation={shown} previous={result.second_opinion ? evaluation ?? undefined : undefined} />
          {result.second_opinion && evaluation && (
            <details className="original-evaluation">
              <summary>{t("study.originalEval")}</summary>
              <EvaluationView evaluation={evaluation} />
            </details>
          )}
        </section>
      )}
      {result.repeat && (
        <section className="evaluation repeat-evaluation" aria-label={t("study.repeat.evalTitle")}>
          <h3>{t("study.repeat.evalTitle")}</h3>
          <EvaluationView evaluation={result.repeat} />
        </section>
      )}

      {/* 4. The reference answer: open when it's needed, a tap away otherwise. */}
      <details className="reference" open={!outcome || outcome === "AGAIN" || repeating}>
        <summary>{t("study.referenceSummary")}</summary>
        <p className="reading">{result.reference.expected_knowledge}</p>
        {result.reference.essential_points.length > 0 && (
          <Points title={t("study.keyPoints")} points={result.reference.essential_points} />
        )}
        <Sources sources={result.reference.sources} openSource={openSource} />
      </details>

      {/* 5. What to do now. */}
      {repeating && !disputing && (
        <section className="repeat-panel" aria-labelledby="repeat-title">
          <h3 id="repeat-title">{t("study.repeat.title")}</h3>
          <p className="hint">{t("study.repeat.body")}</p>
          <label htmlFor="repeat-text">{t("study.repeat.label")}</label>
          <textarea id="repeat-text" rows={4} value={again} maxLength={10000} onChange={(e) => setDraft({ answerId: result.answer_id, text: e.target.value })} />
          <div className="actions">
            <button type="button" className="primary" disabled={s.working || !again.trim()} onClick={() => void s.repeat(again.trim())}>
              {t("study.repeat.submit")}
            </button>
            <button type="button" className="link" disabled={s.working} onClick={() => setSelfGradingFor(result.answer_id)}>
              {t("study.repeat.selfGrade")}
            </button>
          </div>
          <ErrorBanner error={s.error} />
        </section>
      )}
      {gradeMode ? (
        <section className="grades" aria-label={t("study.yourGrade")}>
          {showDispute && !result.second_opinion && (
            <DisputeForm working={s.working} onAsk={s.dispute} testAi={evaluation?.ai_provider === "mock"} />
          )}
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
                {t("study.retryEval")}
              </button>
            )}
            {disputing && (
              <button type="button" className="link" onClick={() => setDisputing(false)}>
                {t("common.cancel")}
              </button>
            )}
            {result.needs_self_grade && (
              <button type="button" className="link" disabled={s.working} onClick={() => void s.skip()}>
                {t("study.skipNow")}
              </button>
            )}
            <button type="button" className="study-concept" onClick={() => openConcept(card.concept_id)}>
              <Icon name="book" size={18} /> {t("study.studyConcept")}
            </button>
          </div>
        </section>
      ) : (
        <div className="result-bar">
          {!repeating && (
            <button ref={continueButton} type="button" className="primary result-continue" disabled={s.working} onClick={() => void s.loadNext()}>
              {t("common.continue")} <kbd>Enter</kbd>
            </button>
          )}
          <button type="button" className="study-concept" onClick={() => openConcept(card.concept_id)}>
            <Icon name="book" size={18} /> {t("study.studyConcept")}
          </button>
          {!repeating && (
            <button type="button" className="link" disabled={s.working} onClick={() => setDisputing(true)}>
              {t("study.disagree")}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function ScheduleNote({ result }: { result: AnswerView }) {
  const { t } = useI18n();
  const schedule = result.schedule;
  if (schedule) {
    if (schedule.next_state === "NEW") {
      return <p className="hint">{t("study.notMemorized")}</p>;
    }
    return (
      <p className="hint">
        {t("study.levelNext", { from: schedule.previous_level, to: schedule.next_level, when: dateTime(schedule.next_due_at) })}
      </p>
    );
  }
  if (result.intent === "PRACTICE" && result.final_outcome) {
    return <p className="hint">{t("study.practiceNote")}</p>;
  }
  return null;
}

function Finished({ s, onClose }: { s: Session; onClose: () => void }) {
  const { t } = useI18n();
  const { outcomeLabel } = useLabels();
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
      <h2>{t("study.complete")}</h2>
      {s.session && s.session.xp_earned > 0 && (
        <p className="xp-chip">
          <XpIcon /> {t("study.xpSessionPlus", { n: s.session.xp_earned })}
        </p>
      )}
      <p>
        {t("study.answeredIn", { answers: t(answered === 1 ? "unit.answer.one" : "unit.answer.other", { n: answered }), min: minutes })}
        {answered > 0 && ` ${t("study.wentWell", { n: wentWell })}`}
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
            ? t("study.steady")
            : t("study.comeBack")}
        </p>
      )}
      {dueNow.data !== undefined && (
        <p className="hint">
          {dueNow.data > 0
            ? t("study.stillDue", { n: dueNow.data, min: studyMinutes(dueNow.data) })
            : t("study.nothingDue")}
        </p>
      )}
      <button type="button" className="primary" onClick={onClose}>
        {t("study.done")}
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
  const { t } = useI18n();
  if (sources.length === 0) return null;
  return (
    <section className="sources">
      <h3>{t("study.sources")}</h3>
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
  const { t } = useI18n();
  const potential = card.potential_xp;
  if (!potential) return null;
  if (!potential.eligible) {
    return (
      <span className="potential muted" title={t("study.noXp")}>
        {t("study.noXpShort")}
        <span className="sr-only"> {t("study.noXp")}</span>
      </span>
    );
  }
  const revealed = card.hint?.revealed ?? false;
  return (
    <span className="potential" title={t("study.levelXp", { level: potential.level })}>
      <span className="xp-chip">
        <XpIcon /> {t("study.correctXp", { n: revealed ? potential.xp_with_hint : potential.xp })}
      </span>
      {revealed && <span className="hint">{t("study.halfXp")}</span>}
    </span>
  );
}

/**
 * "Need a nudge?": the cost (half XP) is stated first, then the hint shows how many points the
 * answer has to cover and a key term from each. The server records the reveal.
 */
function HintBox({ card, s, disabled, revealedOnly = false, askOnly = false }: { card: Card; s: Session; disabled: boolean; revealedOnly?: boolean; askOnly?: boolean }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const hint = card.hint;
  if (!hint) return null;
  if (hint.revealed) {
    if (askOnly) return null;
    const terms = hint.terms ?? [];
    return (
      <div className="hint-card hint-reveal" role="note" aria-label={t("study.hintLabel")}>
        <span className="hint-title">
          <Icon name="bulb" size={18} /> {t("study.hintLabel")}
        </span>
        {hint.point_count ? <p>{t(hint.point_count === 1 ? "study.hintPoints.one" : "study.hintPoints.other", { n: hint.point_count })}</p> : null}
        {terms.length > 0 ? (
          <>
            <span className="hint">{t("study.hintThink")}</span>
            <span className="hint-chips">
              {terms.map((term) => (
                <span key={term} className="hint-chip">
                  {term}
                </span>
              ))}
            </span>
          </>
        ) : (
          hint.text && <p>{hint.text}</p>
        )}
      </div>
    );
  }
  if (!hint.available || revealedOnly) return null;
  if (!confirming) {
    return (
      <button type="button" className="help-chip hint-ask" disabled={disabled} onClick={() => setConfirming(true)}>
        <Icon name="bulb" size={18} /> {t("study.showHint")}
      </button>
    );
  }
  return (
    <div className="hint-confirm hint-reveal">
      <p>{t("study.hintHalves")}</p>
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
          {t("study.revealHint")}
        </button>
        <button type="button" className="link" onClick={() => setConfirming(false)}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

function Award({ result }: { result: AnswerView }) {
  const { t } = useI18n();
  const xp = result.xp;
  if (!xp) return null;
  if (!xp.correct) {
    const selfGraded = result.override_outcome !== null && result.resolved_outcome === null;
    return (
      <p className="award award-pop" aria-live="polite">
        <span className="xp-chip">
          <XpIcon /> {t("study.plusZero")}
        </span>
        <span className="hint">
          {selfGraded
            ? t("study.onlyCorrectSelf")
            : t("study.onlyCorrect")}
        </span>
      </p>
    );
  }
  const parts = [t("study.awardCorrect"), `+${xp.xp} XP`];
  if (xp.hint_used) parts.push(t("study.awardHint"));
  return (
    <p className="award award-pop" aria-live="polite">
      <span className="xp-chip">
        <XpIcon /> {parts.join(" \u00b7 ")}
      </span>
      {xp.level !== null && xp.level !== undefined && (
        <span className="hint">{xp.hint_used ? t("study.levelXpHalf", { level: xp.level, base: xp.base_xp }) : t("study.levelXp", { level: xp.level })}</span>
      )}
    </p>
  );
}

function ConsolidationDone({ s, onClose }: { s: Session; onClose: () => void }) {
  const { t } = useI18n();
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
      <h2>{t("study.batchDone")}</h2>
      <dl className="summary-grid">
        <div>
          <dt>{t("study.correctAnswers")}</dt>
          <dd>
            {correct} / {rounds}
          </dd>
        </div>
        <div>
          <dt>{t("study.xpThisSession")}</dt>
          <dd>+{s.session?.xp_earned ?? 0}</dd>
        </div>
        <div>
          <dt>{t("study.whatNext")}</dt>
          <dd style={{ fontSize: "1rem", fontWeight: 500 }}>
            {t("study.whatNextBody")}
          </dd>
        </div>
      </dl>
      <p className="hint">
        {waiting > 0
          ? t("study.batchNotAll", { waiting: t(waiting === 1 ? "study.waiting.one" : "study.waiting.other", { n: waiting }) })
          : t("study.allRounds")}
      </p>
      <div className="actions">
        {waiting > 0 && conceptId && (
          <Link className="button learn" to={`/courses/${courseId}/concepts/${conceptId}`}>
            {t("study.nextBatch")}
          </Link>
        )}
        <button type="button" className={waiting > 0 ? undefined : "primary"} onClick={onClose}>
          {t("study.done")}
        </button>
      </div>
    </div>
  );
}

/**
 * "Study this concept" before answering. Seeing the concept shows the answer, so where a hint
 * exists it is recorded first (half XP), exactly like "Show hint"; the user is told before.
 */
function StudyConceptButton({
  card,
  s,
  disabled,
  openConcept,
}: {
  card: Card;
  s: Session;
  disabled: boolean;
  openConcept: (conceptId: string) => void;
}) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const costsXp = Boolean(card.hint?.available && !card.hint.revealed && card.potential_xp?.eligible);
  if (confirming) {
    return (
      <div className="hint-confirm hint-reveal" role="note">
        <p>{t("study.conceptCosts")}</p>
        <div className="actions" style={{ marginTop: 0 }}>
          <button
            type="button"
            className="primary"
            disabled={disabled || s.working}
            onClick={() => {
              void s.revealHint().then(() => openConcept(card.concept_id));
              setConfirming(false);
            }}
          >
            {t("study.openConcept")}
          </button>
          <button type="button" className="link" onClick={() => setConfirming(false)}>
            {t("common.cancel")}
          </button>
        </div>
      </div>
    );
  }
  return (
    <button type="button" className="help-chip" disabled={disabled} onClick={() => (costsXp ? setConfirming(true) : openConcept(card.concept_id))}>
      <Icon name="book" size={18} /> {t("study.dontRemember")}
    </button>
  );
}

function ReferenceDrawing({ itemId }: { itemId: string }) {
  const { t } = useI18n();
  return (
    <AuthImage
      queryKey={["reference-drawing", itemId]}
      load={() => learningItems.referenceDrawing(itemId)}
      alt={t("study.refDrawing")}
      className="drawing-image"
    />
  );
}
