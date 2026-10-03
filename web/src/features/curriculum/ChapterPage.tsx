import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { courses, curriculum, progress, reorder } from "../../api/endpoints";
import { EditableTitle } from "../../components/EditableTitle";
import { QueryState } from "../../components/QueryState";
import { SortableList } from "../../components/SortableList";
import { CurriculumBlock, MemoryBlock } from "../../components/ProgressBlocks";
import { MaterialPanel } from "../material/MaterialPanel";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";
import { Breadcrumbs } from "./Consolidate";

export function ChapterPage() {
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

  return (
    <div className="page">
      <QueryState query={outline}>
        {(chapters) => {
          const chapter = chapters.find((c) => c.id === chapterId);
          if (!chapter) return <p className="state">This chapter no longer exists.</p>;
          return (
            <>
              <Breadcrumbs courseId={courseId} chapterId={chapter.id} current={chapter.title} />
              <header className="page-header">
                <EditableTitle
                  title={chapter.title}
                  description={chapter.description}
                  label="chapter"
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
                  <h2>Topics</h2>
                  <button type="button" className="primary" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
                    {analyze.isPending ? "Starting analysis…" : "Analyze new material"}
                  </button>
                </header>
                <p className="hint">
                  The AI proposes topics and concepts from material not analyzed yet. You review the proposal before anything
                  changes.
                </p>
                {analyze.error && (
                  <p className="banner error" role="alert">
                    {analyze.error instanceof ApiError && analyze.error.status === 409
                      ? "There's no new study material to analyze in this chapter. Upload material first."
                      : analyze.error instanceof ApiError
                        ? analyze.error.message
                        : "Something went wrong."}
                  </p>
                )}
                {chapter.topics.length === 0 ? (
                  <p className="hint">No topics yet. Upload material below, then analyze it.</p>
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
                          {topic.concepts.filter((c) => c.study_state === "ACTIVE").length} of {topic.concepts.length} concepts active
                        </span>
                      </>
                    )}
                  />
                )}
              </section>
              <MaterialPanel courseId={courseId} chapterId={chapterId} />
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
