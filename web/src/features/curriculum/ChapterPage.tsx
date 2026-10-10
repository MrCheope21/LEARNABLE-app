import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { courses, curriculum, progress, reorder } from "../../api/endpoints";
import { useReadOnlyCourse } from "../../components/CourseAccess";
import { useI18n } from "../../i18n";
import { EditableTitle } from "../../components/EditableTitle";
import { QueryState } from "../../components/QueryState";
import { SortableList } from "../../components/SortableList";
import { CurriculumBlock, MemoryBlock } from "../../components/ProgressBlocks";
import { MaterialPanel } from "../material/MaterialPanel";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";
import { Breadcrumbs } from "./Consolidate";

export function ChapterPage() {
  const { t } = useI18n();
  const { courseId = "", chapterId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const courseProgress = useQuery({ queryKey: courseProgressKey(courseId), queryFn: () => progress.course(courseId) });
  const analyze = useMutation({
    mutationFn: () => curriculum.generate(courseId, chapterId),
    onSuccess: (proposal) => navigate(`/courses/${courseId}/proposals/${proposal.id}`),
  });
  const chapterProgress = courseProgress.data?.chapters.find((c) => c.id === chapterId);
  const readOnly = useReadOnlyCourse();

  return (
    <div className="page">
      <QueryState query={outline}>
        {(chapters) => {
          const chapter = chapters.find((c) => c.id === chapterId);
          if (!chapter) return <p className="state">{t("chapter.gone")}</p>;
          return (
            <>
              <Breadcrumbs courseId={courseId} chapterId={chapter.id} current={chapter.title} />
              <header className="page-header">
                <EditableTitle
                  title={chapter.title}
                  description={chapter.description}
                  label={t("label.chapter")}
                  onSave={async (values) => {
                    await courses.updateChapter(chapter.id, values);
                    refreshTitles(queryClient, courseId);
                  }}
                />
              </header>
              {chapterProgress && (
                <div className="stat-grid">
                  <CurriculumBlock curriculum={chapterProgress.curriculum} />
                  <MemoryBlock memory={chapterProgress.memory} />
                </div>
              )}
              <section className="card">
                <header className="card-header">
                  <h2>{t("chapter.topics")}</h2>
                  {!readOnly && (
                    <button type="button" className="primary" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
                      {analyze.isPending ? t("chapter.starting") : t("chapter.analyze")}
                    </button>
                  )}
                </header>
                {!readOnly && (
                  <p className="hint">
                    {t("chapter.analyzeHint")}
                  </p>
                )}
                {analyze.error && (
                  <p className="banner error" role="alert">
                    {analyze.error instanceof ApiError && analyze.error.status === 409
                      ? t("chapter.noMaterial")
                      : analyze.error instanceof ApiError
                        ? analyze.error.message
                        : t("error.generic")}
                  </p>
                )}
                {chapter.topics.length === 0 ? (
                  <p className="hint">{t("chapter.empty")}</p>
                ) : (
                  <SortableList
                    items={chapter.topics}
                    itemLabel={(topic) => topic.title}
                    onReorder={async (ids) => {
                      await reorder.topics(chapterId, ids);
                      refreshTitles(queryClient, courseId);
                    }}
                    renderItem={(topic) => (
                      <>
                        <Link to={`/courses/${courseId}/topics/${topic.id}`}>{topic.title}</Link>
                        <span className="row-meta">
                          {t("chapter.topicMeta", { active: topic.concepts.filter((c) => c.study_state === "ACTIVE").length, total: topic.concepts.length })}
                        </span>
                      </>
                    )}
                  />
                )}
              </section>
              {!readOnly && <MaterialPanel courseId={courseId} chapterId={chapterId} />}
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
