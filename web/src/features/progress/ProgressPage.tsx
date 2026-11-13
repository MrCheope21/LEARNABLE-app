import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { courses, progress } from "../../api/endpoints";
import type { MessageKey } from "../../i18n/messages/en";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { CurriculumBlock, MemoryBlock, ReviewLoadBlock } from "../../components/ProgressBlocks";
import type { Schemas } from "../../api/client";
import { studyMinutes } from "../../components/labels";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { homeKey } from "../home/HomePage";

/**
 * Progress for one Course at a time: curriculum progress and memory progress side by side,
 * never merged into one score (docs/PROJECT_SPEC.md §54, §67).
 */
export function ProgressPage() {
  const { t } = useI18n();
  const home = useQuery({ queryKey: homeKey, queryFn: progress.home });
  const [selected, setSelected] = useState<string | null>(null);
  const courseId = selected ?? home.data?.courses[0]?.course_id ?? null;
  const courseProgress = useQuery({
    queryKey: ["progress", courseId],
    queryFn: () => progress.course(courseId as string),
    enabled: courseId !== null,
  });
  const summary = home.data?.courses.find((c) => c.course_id === courseId);

  return (
    <div className="page">
      <div className="page-header">
        <h1>{t("nav.progress")}</h1>
      </div>
      <QueryState query={home}>
        {(data) =>
          data.courses.length === 0 ? (
            <p className="state">{t("prog.empty")}</p>
          ) : (
            <>
              {data.courses.length > 1 && (
                <label className="inline-form">
                  {t("course.fallback")}
                  <select value={courseId ?? ""} onChange={(e) => setSelected(e.target.value)}>
                    {data.courses.map((c) => (
                      <option key={c.course_id} value={c.course_id}>
                        {c.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <QueryState query={courseProgress}>
                {(p) => (
                  <>
                    <Headline progress={p} />
                    <ExamCard courseId={p.course_id} exam={p.exam ?? null} />
                    <ChapterBars chapters={p.chapters} />
                    <details className="card progress-details">
                      <summary>{t("prog.details")}</summary>
                      <div className="stat-grid">
                        <ReviewLoadBlock load={p.review_load} />
                        <CurriculumBlock curriculum={p.curriculum} />
                        <MemoryBlock memory={p.memory} />
                      </div>
                    </details>
                    {summary && summary.weak_concepts.length > 0 && (
                      <section className="card">
                        <h2>{t("prog.weakConcepts")}</h2>
                        <ul>
                          {summary.weak_concepts.map((w) => (
                            <li key={w.id}>
                              {w.title} <span className="hint">· {t("prog.weakMeta", { lapses: w.lapses, hard: w.marked_hard })}</span>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                  </>
                )}
              </QueryState>
            </>
          )
        }
      </QueryState>
    </div>
  );
}

/** The three things worth knowing at a glance: what to do today, how far in, how well known. */
function Headline({ progress }: { progress: Schemas["CourseProgress"] }) {
  const { t } = useI18n();
  const due = progress.review_load.due_now + progress.review_load.later_today;
  const started = progress.memory.items_trained;
  const total = started + progress.review_load.new_to_learn;
  const share = total > 0 ? Math.round((started / total) * 100) : 0;
  const mastery = Math.round((progress.memory.mastery ?? 0) * 100);
  return (
    <dl className="headline">
      <div className={due > 0 ? "headline-item due" : "headline-item"}>
        <dt>{t("prog.dueToday")}</dt>
        <dd>{due.toLocaleString()}</dd>
        <span className="hint">{due > 0 ? t("pb.minutes", { n: studyMinutes(due) }) : t("planner.allClear")}</span>
      </div>
      <div className="headline-item">
        <dt>{t("prog.started")}</dt>
        <dd>{share}%</dd>
        <span className="hint">{t("prog.startedHint", { done: started, total })}</span>
        <span className="mini-bar" aria-hidden="true">
          <span style={{ width: `${share}%` }} />
        </span>
      </div>
      <div className="headline-item">
        <dt>{t("prog.known")}</dt>
        <dd>{mastery}%</dd>
        <span className="hint">{t("prog.knownHint")}</span>
        <span className="mini-bar good" aria-hidden="true">
          <span style={{ width: `${mastery}%` }} />
        </span>
      </div>
    </dl>
  );
}

/**
 * Exam mode: with a date, how many new questions a day get you there, and whether the last
 * week's pace is enough.
 */
function ExamCard({ courseId, exam }: { courseId: string; exam: Schemas["ExamPlan"] | null }) {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [date, setDate] = useState(exam?.date ?? "");
  const save = useMutation({
    mutationFn: (value: string | null) => courses.setExamDate(courseId, value),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["progress", courseId] });
    },
  });
  const today = new Date().toISOString().slice(0, 10);
  if (!exam || editing) {
    return (
      <form
        className="card exam-card"
        onSubmit={(e) => {
          e.preventDefault();
          if (date) save.mutate(date);
        }}
      >
        <h2>{t("exam.title")}</h2>
        <p className="hint">{t("exam.intro")}</p>
        <div className="inline-field">
          <input type="date" value={date} min={today} aria-label={t("exam.date")} onChange={(e) => setDate(e.target.value)} />
          <button type="submit" className="primary" disabled={!date || save.isPending}>
            {t("common.save")}
          </button>
          {exam && (
            <>
              <button type="button" className="link danger" disabled={save.isPending} onClick={() => save.mutate(null)}>
                {t("exam.remove")}
              </button>
              <button type="button" className="link" onClick={() => setEditing(false)}>
                {t("common.cancel")}
              </button>
            </>
          )}
        </div>
        <ErrorBanner error={save.error} />
      </form>
    );
  }
  const day = new Date(`${exam.date}T00:00:00Z`).toLocaleDateString(language, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  return (
    <section className={`card exam-card ${exam.status}`} aria-labelledby="exam-title">
      <div className="card-header">
        <h2 id="exam-title">{t("exam.title")}</h2>
        <button type="button" className="link" onClick={() => setEditing(true)}>
          {t("exam.change")}
        </button>
      </div>
      <p className="exam-count">
        <strong>{exam.status === "past" ? "–" : exam.days_left}</strong> {exam.status === "past" ? t("exam.past") : t("exam.daysTo", { date: day })}
      </p>
      <p className={`exam-status ${exam.status}`}>{t(`exam.status.${exam.status}` as MessageKey, { n: exam.new_per_day, pace: exam.pace.toLocaleString(language), left: exam.new_left })}</p>
    </section>
  );
}

type Memory = Schemas["MemoryProgress"];
const PARTS = ["mastered", "review", "learning", "new"] as const;

function counts(memory: Memory): Record<(typeof PARTS)[number], number> {
  return { mastered: memory.mastered, review: memory.review + memory.relearning, learning: memory.learning, new: memory.new };
}

/** One bar: how the questions of a chapter (or a topic) divide by how well they are known. */
function KnowledgeBar({ memory, label }: { memory: Memory; label: string }) {
  const { t } = useI18n();
  const n = counts(memory);
  const total = PARTS.reduce((sum, part) => sum + n[part], 0);
  const known = total > 0 ? Math.round((n.mastered / total) * 100) : 0;
  return (
    <>
      <span className="know-bar" role="img" aria-label={t("prog.barAria", { name: label, known, total })}>
        {total === 0 ? null : PARTS.filter((part) => n[part] > 0).map((part) => <span key={part} className={`seg seg-${part}`} style={{ flexGrow: n[part] }} />)}
      </span>
      <span className="know-figure">{total === 0 ? "–" : `${known}%`}</span>
    </>
  );
}

/**
 * "By chapter": each chapter is one bar, coloured by how well its questions are known, with the
 * share already mastered next to it. Opening a chapter shows the same bar for each topic.
 */
function ChapterBars({ chapters }: { chapters: Schemas["CourseProgress"]["chapters"] }) {
  const { t } = useI18n();
  const { memoryStateLabel } = useLabels();
  const legend = { mastered: memoryStateLabel.MASTERED, review: memoryStateLabel.REVIEW, learning: memoryStateLabel.LEARNING, new: memoryStateLabel.NEW };
  if (chapters.length === 0) return null;
  return (
    <section className="card know-card" aria-labelledby="know-title">
      <h2 id="know-title">{t("prog.byChapter")}</h2>
      <p className="hint">{t("prog.barHint")}</p>
      <ul className="know-legend" aria-hidden="true">
        {PARTS.map((part) => (
          <li key={part}>
            <span className={`seg seg-${part}`} /> {legend[part]}
          </li>
        ))}
      </ul>
      <div className="know-list">
        {chapters.map((chapter) => (
          <details key={chapter.id} className="know-chapter">
            <summary className="know-row">
              <span className="know-name">{chapter.title}</span>
              <KnowledgeBar memory={chapter.memory} label={chapter.title} />
            </summary>
            {chapter.topics.map((topic) => (
              <div key={topic.id} className="know-row topic">
                <span className="know-name">{topic.title}</span>
                <KnowledgeBar memory={topic.memory} label={topic.title} />
              </div>
            ))}
          </details>
        ))}
      </div>
    </section>
  );
}
