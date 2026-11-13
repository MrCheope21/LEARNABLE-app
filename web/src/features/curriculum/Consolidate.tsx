import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { Link, useNavigate } from "react-router-dom";
import { concepts, courses } from "../../api/endpoints";
import { ErrorBanner } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { outlineKey } from "./CourseLayout";

export const consolidationKey = (conceptId: string) => ["consolidation", conceptId] as const;

/**
 * "I have studied this concept" (docs/SCHEDULING.md §4a). Opening or activating a concept
 * doesn't count as studying it: the user says so, and each waiting item is then asked three
 * times in a row. Shows the batch size before starting; resumes an unfinished batch instead of
 * starting over.
 */
export function ConsolidatePanel({ courseId, conceptId, active }: { courseId: string; conceptId: string; active: boolean }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const plan = useQuery({ queryKey: consolidationKey(conceptId), queryFn: () => concepts.consolidationPlan(conceptId) });
  const start = useMutation({
    mutationFn: () => concepts.startConsolidation(conceptId),
    onSuccess: (session) => {
      void queryClient.invalidateQueries({ queryKey: consolidationKey(conceptId) });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/study/${courseId}?session=${session.id}`);
    },
  });
  const p = plan.data;
  if (!active || !p) return null;

  if (p.unfinished) {
    const left = p.unfinished.total - p.unfinished.position;
    const items = t(p.unfinished_items === 1 ? "unit.item.one" : "unit.item.other", { n: p.unfinished_items });
    const answersLeft = t(left === 1 ? "unit.answer.one" : "unit.answer.other", { n: left });
    return (
      <section className="card consolidate" aria-labelledby="consolidate-title">
        <h2 id="consolidate-title">{t("consolidate.continue")}</h2>
        <p>{t("consolidate.unfinished", { items, left: answersLeft })}</p>
        <div className="actions">
          <button type="button" className="learn" disabled={start.isPending} onClick={() => start.mutate()}>
            {t("consolidate.resume")}
          </button>
        </div>
        <ErrorBanner error={start.error} />
      </section>
    );
  }
  if (p.new_items === 0) {
    return (
      <section className="card consolidate" aria-labelledby="consolidate-title">
        <h2 id="consolidate-title">{t("consolidate.doneTitle")}</h2>
        <p className="hint">{t("consolidate.doneBody")}</p>
      </section>
    );
  }
  return (
    <section className="card consolidate" aria-labelledby="consolidate-title">
      <div className="title-row">
        <h2 id="consolidate-title">{t("consolidate.title")}</h2>
        <HelpTip text="help.consolidate" topic={t("consolidate.title")} guide="study" />
      </div>
      <p>{t("consolidate.body", { n: p.rounds_per_item })}</p>
      <p className="hint">
        {t("consolidate.batch", {
          items: t(p.batch_items === 1 ? "unit.item.one" : "unit.item.other", { n: p.batch_items }),
          answers: t(p.answers_in_batch === 1 ? "unit.answer.one" : "unit.answer.other", { n: p.answers_in_batch }),
        })}
        {p.remaining_after_batch > 0 && ` · ${t(p.remaining_after_batch === 1 ? "consolidate.more.one" : "consolidate.more.other", { n: p.remaining_after_batch })}`}
      </p>
      <div className="actions">
        <button type="button" className="learn" disabled={start.isPending} onClick={() => start.mutate()}>
          {t("consolidate.button")}
        </button>
      </div>
      <ErrorBanner error={start.error} />
    </section>
  );
}

/** Course › Chapter › Topic › Concept, from the cached outline. */
export function Breadcrumbs({
  courseId,
  chapterId,
  topicId,
  current,
}: {
  courseId: string;
  chapterId?: string;
  topicId?: string;
  current: string;
}) {
  const { t } = useI18n();
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const chapter = outline.data?.find((c) => c.id === chapterId || c.topics.some((t) => t.id === topicId));
  const topic = chapter?.topics.find((t) => t.id === topicId);
  return (
    <nav aria-label={t("breadcrumb.aria")}>
      <ol className="breadcrumb">
        <li>
          <Link to={`/courses/${courseId}`}>{course.data?.title ?? t("course.fallback")}</Link>
        </li>
        {chapter && (
          <li>
            <Link to={`/courses/${courseId}/chapters/${chapter.id}`}>{chapter.title}</Link>
          </li>
        )}
        {topic && (
          <li>
            <Link to={`/courses/${courseId}/topics/${topic.id}`}>{topic.title}</Link>
          </li>
        )}
        <li aria-current="page">{current}</li>
      </ol>
    </nav>
  );
}
