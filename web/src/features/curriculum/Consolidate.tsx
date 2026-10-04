import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { Link, useNavigate } from "react-router-dom";
import { concepts, courses } from "../../api/endpoints";
import { ErrorBanner } from "../../components/QueryState";
import { outlineKey } from "./CourseLayout";

export const consolidationKey = (conceptId: string) => ["consolidation", conceptId] as const;

/**
 * "I have studied this concept" (docs/SCHEDULING.md §4a). Opening or activating a concept
 * doesn't count as studying it: the user says so, and each waiting item is then asked three
 * times in a row. Shows the batch size before starting; resumes an unfinished batch instead of
 * starting over.
 */
export function ConsolidatePanel({ courseId, conceptId, active }: { courseId: string; conceptId: string; active: boolean }) {
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
    return (
      <section className="card consolidate" aria-labelledby="consolidate-title">
        <h2 id="consolidate-title">Continue consolidation</h2>
        <p>
          Your batch of {p.unfinished_items} {p.unfinished_items === 1 ? "item" : "items"} is unfinished: {left}{" "}
          {left === 1 ? "answer" : "answers"} left. Rounds you've already answered are kept.
        </p>
        <div className="actions">
          <button type="button" className="learn" disabled={start.isPending} onClick={() => start.mutate()}>
            Resume
          </button>
        </div>
        <ErrorBanner error={start.error} />
      </section>
    );
  }
  if (p.new_items === 0) {
    return (
      <section className="card consolidate" aria-labelledby="consolidate-title">
        <h2 id="consolidate-title">Consolidated</h2>
        <p className="hint">
          Every item in this concept has had its consolidation rounds. They come back in your reviews when they're due.
        </p>
      </section>
    );
  }
  return (
    <section className="card consolidate" aria-labelledby="consolidate-title">
      <div className="title-row">
        <h2 id="consolidate-title">Studied this concept?</h2>
        <HelpTip text="help.consolidate" topic="Studied this concept?" guide="study" />
      </div>
      <p>
        Read its learning items below first. When you're ready, each question is asked <strong>{p.rounds_per_item} times in a row</strong>,
        with feedback after every round.
      </p>
      <p className="hint">
        This batch: {p.batch_items} {p.batch_items === 1 ? "item" : "items"} · {p.answers_in_batch} answers
        {p.remaining_after_batch > 0 &&
          ` · ${p.remaining_after_batch} more ${p.remaining_after_batch === 1 ? "item waits" : "items wait"} for a later batch`}
      </p>
      <div className="actions">
        <button type="button" className="learn" disabled={start.isPending} onClick={() => start.mutate()}>
          I have studied this concept
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
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const chapter = outline.data?.find((c) => c.id === chapterId || c.topics.some((t) => t.id === topicId));
  const topic = chapter?.topics.find((t) => t.id === topicId);
  return (
    <nav aria-label="Breadcrumb">
      <ol className="breadcrumb">
        <li>
          <Link to={`/courses/${courseId}`}>{course.data?.title ?? "Course"}</Link>
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
