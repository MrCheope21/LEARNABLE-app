import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { courses, progress } from "../../api/endpoints";
import { EditableTitle } from "../../components/EditableTitle";
import { QueryState } from "../../components/QueryState";
import { percent, studyStateLabel } from "../../components/labels";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";
import { Breadcrumbs } from "./Consolidate";

export function TopicPage() {
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
          if (!topic) return <p className="state">This topic no longer exists.</p>;
          return (
            <>
              <Breadcrumbs courseId={courseId} topicId={topic.id} current={topic.title} />
              <header className="page-header">
                <EditableTitle
                  title={topic.title}
                  description={topic.description}
                  label="topic"
                  onSave={async (values) => {
                    await courses.updateTopic(topic.id, values);
                    refreshTitles(queryClient, courseId);
                  }}
                />
              </header>
              <section className="card">
                <h2>Concepts</h2>
                {topic.concepts.length === 0 ? (
                  <p className="hint">No concepts in this topic.</p>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Concept</th>
                        <th scope="col">State</th>
                        <th scope="col">Mastery (estimate)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topic.concepts.map((concept) => {
                        const mastery = topicProgress?.concepts.find((c) => c.id === concept.id)?.memory.mastery;
                        return (
                          <tr key={concept.id}>
                            <td>
                              <Link to={`/courses/${courseId}/concepts/${concept.id}`}>{concept.title}</Link>
                              {concept.needs_source_review && <span className="pill warning">Needs source review</span>}
                            </td>
                            <td>{studyStateLabel[concept.study_state]}</td>
                            <td>{percent(mastery)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </section>
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
