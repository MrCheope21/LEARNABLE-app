import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { courses, progress, reorder } from "../../api/endpoints";
import { EditableTitle } from "../../components/EditableTitle";
import { QueryState } from "../../components/QueryState";
import { SortableList } from "../../components/SortableList";
import { percent } from "../../components/labels";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";
import { Breadcrumbs } from "./Consolidate";

export function TopicPage() {
  const { t } = useI18n();
  const { studyStateLabel } = useLabels();
  const { courseId = "", topicId = "" } = useParams();
  const queryClient = useQueryClient();
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const courseProgress = useQuery({ queryKey: courseProgressKey(courseId), queryFn: () => progress.course(courseId) });
  const topicProgress = courseProgress.data?.chapters.flatMap((c) => c.topics).find((t) => t.id === topicId);

  return (
    <div className="page">
      <QueryState query={outline}>
        {(chapters) => {
          const topic = chapters.flatMap((c) => c.topics).find((t) => t.id === topicId);
          if (!topic) return <p className="state">{t("topic.gone")}</p>;
          return (
            <>
              <Breadcrumbs courseId={courseId} topicId={topic.id} current={topic.title} />
              <header className="page-header">
                <EditableTitle
                  title={topic.title}
                  description={topic.description}
                  label={t("label.topic")}
                  onSave={async (values) => {
                    await courses.updateTopic(topic.id, values);
                    refreshTitles(queryClient, courseId);
                  }}
                />
              </header>
              <section className="card">
                <h2>{t("topic.concepts")}</h2>
                {topic.concepts.length === 0 ? (
                  <p className="hint">{t("topic.empty")}</p>
                ) : (
                  <SortableList
                    items={topic.concepts}
                    itemLabel={(concept) => concept.title}
                    onReorder={async (ids) => {
                      await reorder.concepts(topicId, ids);
                      refreshTitles(queryClient, courseId);
                    }}
                    renderItem={(concept) => (
                      <>
                        <Link to={`/courses/${courseId}/concepts/${concept.id}`}>{concept.title}</Link>
                        {concept.needs_source_review && <span className="pill warning">{t("topic.needsReview")}</span>}
                        <span className="row-meta">
                          {t("topic.conceptMeta", { state: studyStateLabel[concept.study_state], mastery: percent(topicProgress?.concepts.find((c) => c.id === concept.id)?.memory.mastery) })}
                        </span>
                      </>
                    )}
                  />
                )}
              </section>
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
