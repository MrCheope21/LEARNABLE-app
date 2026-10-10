import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { courses, dashboard, progress, reorder } from "../../api/endpoints";
import { useReadOnlyCourse } from "../../components/CourseAccess";
import { EditableTitle } from "../../components/EditableTitle";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { SortableList } from "../../components/SortableList";
import { CurriculumBlock, MemoryBlock, ReviewLoadBlock } from "../../components/ProgressBlocks";
import { percent } from "../../components/labels";
import { useI18n } from "../../i18n";
import { CourseCover, LearnButton, Metric, ReviewButton } from "../courses/CourseParts";
import { studyLink } from "../study/StudyPage";
import { MARKETPLACE_ANCHOR, MarketplacePanel } from "../marketplace/MarketplacePanel";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";

export function CourseOverview() {
  const { t } = useI18n();
  const { courseId = "" } = useParams();
  const queryClient = useQueryClient();
  const courseProgress = useQuery({ queryKey: courseProgressKey(courseId), queryFn: () => progress.course(courseId) });
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const summary = useQuery({ queryKey: ["course-summary", courseId], queryFn: () => dashboard.courseSummary(courseId) });
  const [title, setTitle] = useState("");
  const readOnly = useReadOnlyCourse();
  const addChapter = useMutation({
    mutationFn: () => courses.createChapter(courseId, title.trim(), outline.data?.length ?? 0),
    onSuccess: () => {
      setTitle("");
      void queryClient.invalidateQueries({ queryKey: outlineKey(courseId) });
      void queryClient.invalidateQueries({ queryKey: courseProgressKey(courseId) });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim()) addChapter.mutate();
  };

  return (
    <div className="page">
      <QueryState query={courseProgress}>
        {(data) => (
          <>
            {summary.data && (
              <section className="card course-header" aria-labelledby="course-title">
                <CourseCover id={summary.data.id} title={summary.data.title} />
                <div className="course-body">
                  <EditableTitle
                    title={summary.data.title}
                    description={summary.data.description}
                    label={t("label.course")}
                    headingId="course-title"
                    onSave={async (values) => {
                      await courses.update(courseId, values);
                      refreshTitles(queryClient, courseId);
                    }}
                  />
                  {summary.data.learn.concept && (
                    <p className="course-next">
                      {summary.data.learn.kind === "resume" ? t("card.continue") : t("card.next")}: <strong>{summary.data.learn.concept.title}</strong>
                    </p>
                  )}
                  <Metric done={summary.data.concepts_studied} total={summary.data.concepts_total} label={t("card.conceptsStudied")} />
                  <Metric done={summary.data.items_introduced} total={summary.data.items_trained} label={t("card.itemsIntroduced")} />
                </div>
                <div className="course-actions">
                  <ReviewButton courseId={courseId} due={summary.data.due_now} />
                  <LearnButton courseId={courseId} learn={summary.data.learn} />
                  <Link className="button" to={studyLink(courseId, "PRACTICE", { mode: "MARKED_HARD" })}>
                    {t("course.practiceHard")}
                  </Link>
                  {!readOnly && (
                    <Link className="button" to={{ hash: MARKETPLACE_ANCHOR }} replace>
                      {t("menu.publish")}
                    </Link>
                  )}
                </div>
              </section>
            )}
            <div className="stat-grid">
              <ReviewLoadBlock load={data.review_load} />
              <CurriculumBlock curriculum={data.curriculum} />
              <MemoryBlock memory={data.memory} />
            </div>
            <section className="card">
              <h2>{t("course.chapters")}</h2>
              {data.chapters.length === 0 ? (
                <p className="hint">{t("course.chaptersEmpty")}</p>
              ) : (
                <SortableList
                  items={data.chapters}
                  itemLabel={(chapter) => chapter.title}
                  onReorder={async (ids) => {
                    await reorder.chapters(courseId, ids);
                    refreshTitles(queryClient, courseId);
                  }}
                  renderItem={(chapter) => (
                    <>
                      <Link to={`/courses/${courseId}/chapters/${chapter.id}`}>{chapter.title}</Link>
                      <span className="row-meta">
                        {t("course.chapterMeta", { active: chapter.curriculum.active, total: chapter.curriculum.concepts, mastery: percent(chapter.memory.mastery) })}
                      </span>
                    </>
                  )}
                />
              )}
              {!readOnly && (
              <form className="inline-form" onSubmit={submit}>
                <label className="sr-only" htmlFor="chapter-title">
                  {t("course.newChapter")}
                </label>
                <input
                  id="chapter-title"
                  placeholder={t("course.newChapter")}
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                />
                <button type="submit" disabled={!title.trim() || addChapter.isPending}>
                  {t("course.addChapter")}
                </button>
              </form>
              )}
              <ErrorBanner error={addChapter.error} />
            </section>
            {summary.data && <MarketplacePanel courseId={courseId} courseTitle={summary.data.title} />}
          </>
        )}
      </QueryState>
    </div>
  );
}
