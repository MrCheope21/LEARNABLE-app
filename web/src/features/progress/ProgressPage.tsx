import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { progress } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { CurriculumBlock, MemoryBlock, ReviewLoadBlock } from "../../components/ProgressBlocks";
import { percent } from "../../components/labels";
import { homeKey } from "../home/HomePage";

/**
 * Progress for one Course at a time: curriculum progress and memory progress side by side,
 * never merged into one score (docs/PROJECT_SPEC.md §54, §67).
 */
export function ProgressPage() {
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
      <header className="page-header">
        <h1>Progress</h1>
      </header>
      <QueryState query={home}>
        {(data) =>
          data.courses.length === 0 ? (
            <p className="state">Create a course and start learning to see your progress.</p>
          ) : (
            <>
              {data.courses.length > 1 && (
                <label className="inline-form">
                  Course
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
                    <div className="stat-grid">
                      <ReviewLoadBlock load={p.review_load} />
                      <CurriculumBlock curriculum={p.curriculum} />
                      <MemoryBlock memory={p.memory} />
                    </div>
                    {summary && summary.weak_concepts.length > 0 && (
                      <section className="card">
                        <h2>Weak concepts</h2>
                        <ul>
                          {summary.weak_concepts.map((w) => (
                            <li key={w.id}>
                              {w.title} <span className="hint">· lapses: {w.lapses} · marked hard: {w.marked_hard}</span>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                    <section className="card">
                      <h2>By chapter and topic</h2>
                      <table className="table">
                        <thead>
                          <tr>
                            <th scope="col">Chapter / topic</th>
                            <th scope="col">Concepts active</th>
                            <th scope="col">Items in training</th>
                            <th scope="col">Mastery (estimate)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {p.chapters.flatMap((chapter) => [
                            <tr key={chapter.id} className="group-row">
                              <th scope="row">{chapter.title}</th>
                              <td>
                                {chapter.curriculum.active} of {chapter.curriculum.concepts}
                              </td>
                              <td>{chapter.memory.items_trained}</td>
                              <td>{percent(chapter.memory.mastery)}</td>
                            </tr>,
                            ...chapter.topics.map((topic) => (
                              <tr key={topic.id}>
                                <td className="indent">{topic.title}</td>
                                <td>
                                  {topic.curriculum.active} of {topic.curriculum.concepts}
                                </td>
                                <td>{topic.memory.items_trained}</td>
                                <td>{percent(topic.memory.mastery)}</td>
                              </tr>
                            )),
                          ])}
                        </tbody>
                      </table>
                    </section>
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
