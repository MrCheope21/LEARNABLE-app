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
import { ConceptPanel } from "./ConceptPanel";
import { useI18n } from "../../i18n";
import { DisputeForm } from "./DisputeForm";
import { recognitionLanguage, useDictation } from "./useDictation";
import { EvaluationView } from "./EvaluationView";
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
    limit: 20,
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
  const openSource = (ref: SourceRef) => {
    setConceptPanel(null);
    setSource(ref);
  };
  const openConcept = (conceptId: string) => {
    setSource(null);
    setConceptPanel(conceptId);
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
        <div>
          <Link to="/" className="home-link" aria-label={t("nav.home")}>
            <BrandLogo form="mark" height={28} />
          </Link>
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
          <span className="eyebrow">{t(`study.intent.${intent}` as MessageKey)}</span>
          {card?.round && card.rounds_total ? (
            <span className="round-badge">
              {t("study.round", { n: card.round, total: card.rounds_total })}
            </span>
          ) : null}
          {position !== null && s.session && (
            <span className="counter" aria-label={t("study.progressAria")}>
              {t("study.progress", { n: position, total: s.session.total })}
            </span>
          )}
          {s.session && s.session.xp_earned > 0 && (
            <span className="xp-chip" aria-label={t("study.xpSessionAria", { n: s.session.xp_earned })}>
              <XpIcon /> {t("community.xp", { n: s.session.xp_earned })}
            </span>
          )}
          {s.session && !s.session.affects_schedule && (
            <span className="pill">{t("study.ownReview")}</span>
          )}
        </div>
        <button type="button" onClick={() => void close()}>
          {consolidating ? t("study.leaveResume") : t("study.end")}
        </button>
      </header>

      <div className={source || conceptPanel ? "study-body with-panel" : "study-body"}>
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
        {conceptPanel && <ConceptPanel courseId={courseId} conceptId={conceptPanel} onClose={() => setConceptPanel(null)} />}
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

  return (
    <article className="card">
      <div className="title-row card-top">
        <span className="eyebrow">{card.concept_title}</span>
        <HelpTip text="help.study" topic={t("study.answering")} guide="answer" />
      </div>
      <h2 className="question">{card.question.text}</h2>
      <PotentialXp card={card} />
      <StudyConceptButton card={card} s={s} disabled={submitting} openConcept={openConcept} />
      <HintBox card={card} s={s} disabled={submitting} />
      {card.answer_format === "DRAWING" && (
        <>
          <p className="hint">{t("study.drawHint")}</p>
          <DrawingPad key={card.question.id} onChange={s.setDrawing} disabled={submitting} />
        </>
      )}
      <label className={card.answer_format === "DRAWING" ? "drawing-note-label" : "sr-only"} htmlFor="answer">
        {card.answer_format === "DRAWING" ? t("study.note") : t("study.yourAnswer")}
      </label>
      <textarea
        id="answer"
        ref={editor}
        value={s.draft}
        onChange={(e) => s.setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={submitting}
        rows={card.answer_format === "DRAWING" ? 2 : 9}
        className={card.answer_format === "DRAWING" ? "drawing-note" : undefined}
        placeholder={card.answer_format === "DRAWING" ? t("study.notePlaceholder") : t("study.answerPlaceholder")}
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
        {dictation.supported && card.answer_format !== "DRAWING" && (
          <button
            type="button"
            className={dictation.listening ? "mic listening" : "mic"}
            aria-pressed={dictation.listening}
            disabled={submitting}
            onClick={dictation.listening ? dictation.stop : dictation.start}
          >
            {dictation.listening ? t("study.stopListening") : t("study.speak")}
          </button>
        )}
        <button type="button" className="primary" disabled={!s.canSubmit || submitting} onClick={() => void s.submit()}>
          {submitting ? t("study.evaluating") : t("study.submit")} <kbd>Ctrl/⌘ Enter</kbd>
        </button>
        <button type="button" className="link" disabled={submitting || s.working} onClick={() => void s.skip()}>
          {t("study.skip")}
        </button>
      </div>
      {card.answer_format !== "DRAWING" && (
        <p className="hint">
          {dictation.supported
            ? t("study.dictationOn")
            : t("study.dictationOff")}
        </p>
      )}
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

  return (
    <article className="card result">
      <span className="eyebrow">{card.concept_title}</span>
      <h2 className="question">{card.question.text}</h2>
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

      <header className="outcome" aria-live="polite">
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
      </header>

      <Award result={result} />

      {evaluation && (
        <section className="evaluation" aria-label={t("study.firstEval")}>
          {result.second_opinion && <h3>{t("study.firstEval")}</h3>}
          <EvaluationView evaluation={evaluation} />
        </section>
      )}
      {result.second_opinion && (
        <section className="evaluation second-opinion" aria-label={t("study.secondOpinion")}>
          <h3>{t("study.secondOpinion")}</h3>
          <p className="hint">{t("study.afterObjection", { text: result.second_opinion.user_argument ?? "" })}</p>
          <EvaluationView evaluation={result.second_opinion} />
        </section>
      )}

      <details className="reference" open={!outcome || outcome === "AGAIN" || repeating}>
        <summary>{t("study.referenceSummary")}</summary>
        <p className="reading">{result.reference.expected_knowledge}</p>
        {result.reference.essential_points.length > 0 && (
          <Points title={t("study.keyPoints")} points={result.reference.essential_points} />
        )}
        <Sources sources={result.reference.sources} openSource={openSource} />
      </details>

      <ScheduleNote result={result} />
      <button type="button" className="link" onClick={() => openConcept(card.concept_id)}>
        {t("study.studyConcept")}
      </button>

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
          {showDispute && (
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
          </div>
        </section>
      ) : repeating ? null : (
        <div className="actions">
          <button
            ref={continueButton}
            type="button"
            className="primary"
            disabled={s.working}
            onClick={() => void s.loadNext()}
          >
            {t("common.continue")} <kbd>Enter</kbd>
          </button>
          <button type="button" className="link" disabled={s.working} onClick={() => setDisputing(true)}>
            {t("study.disagree")}
          </button>
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
    return <p className="potential">{t("study.noXp")}</p>;
  }
  const revealed = card.hint?.revealed ?? false;
  return (
    <p className="potential">
      <span className="xp-chip">
        <XpIcon /> {t("study.correctXp", { n: revealed ? potential.xp_with_hint : potential.xp })}
      </span>
      {revealed && <span>{t("study.halfXp")}</span>}
    </p>
  );
}

/** "Show hint": the halving is stated before anything is revealed; the server records it. */
function HintBox({ card, s, disabled }: { card: Card; s: Session; disabled: boolean }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const hint = card.hint;
  if (!hint) return null;
  if (hint.revealed) {
    return (
      <div className="hint-box" role="note" aria-label={t("study.hintLabel")}>
        <span className="eyebrow">{t("study.hintLabel")}</span>
        <span className="hint-text">{hint.text}</span>
      </div>
    );
  }
  if (!hint.available) return <p className="hint">{t("study.noHint")}</p>;
  if (!confirming) {
    return (
      <div>
        <button type="button" className="link" disabled={disabled} onClick={() => setConfirming(true)}>
          {t("study.showHint")}
        </button>
      </div>
    );
  }
  return (
    <div className="hint-box">
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
      {xp.ordinal !== null && (
        <span className="hint">
          {xp.hint_used ? t("study.ordinalHalf", { n: xp.ordinal, base: xp.base_xp }) : t("study.ordinal", { n: xp.ordinal })}
        </span>
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
      <div className="hint-box" role="note">
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
    <div>
      <button
        type="button"
        className="link"
        disabled={disabled}
        onClick={() => (costsXp ? setConfirming(true) : openConcept(card.concept_id))}
      >
        {t("study.dontRemember")}
      </button>
    </div>
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
