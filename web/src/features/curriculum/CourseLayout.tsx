import { useQuery, type QueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { courses } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { studyStateLabel } from "../../components/labels";

export const outlineKey = (courseId: string) => ["outline", courseId] as const;
export const courseProgressKey = (courseId: string) => ["progress", courseId] as const;

/** After a rename: every view that shows a course, chapter, topic or concept title. */
export function refreshTitles(queryClient: QueryClient, courseId: string) {
  for (const key of [outlineKey(courseId), courseProgressKey(courseId), ["course", courseId], ["course-summary", courseId], ["concept"], ["dashboard"], ["courses"]]) {
    void queryClient.invalidateQueries({ queryKey: key });
  }
}

/**
 * A Course workspace: the whole curriculum tree stays visible on the left while you work on
 * one Chapter, Topic or Concept on the right (desktop-first, docs/WEB_ARCHITECTURE.md §5).
 */
export function CourseLayout() {
  const { courseId = "" } = useParams();
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });

  return (
    <div className="course-workspace">
      <nav className="tree" aria-label="Curriculum">
        <NavLink end to={`/courses/${courseId}`} className="tree-course">
          {course.data?.title ?? "Course"}
        </NavLink>
        <QueryState query={outline} label="Loading curriculum…">
          {(chapters) => (
            <ul>
              {chapters.map((chapter) => (
                <li key={chapter.id}>
                  <NavLink to={`/courses/${courseId}/chapters/${chapter.id}`} className="tree-chapter">
                    {chapter.title}
                  </NavLink>
                  <ul>
                    {chapter.topics.map((topic) => (
                      <li key={topic.id}>
                        <NavLink to={`/courses/${courseId}/topics/${topic.id}`} className="tree-topic">
                          {topic.title}
                        </NavLink>
                        <ul>
                          {topic.concepts.map((concept) => (
                            <li key={concept.id}>
                              <NavLink
                                to={`/courses/${courseId}/concepts/${concept.id}`}
                                className={`tree-concept state-${concept.study_state.toLowerCase()}`}
                                title={studyStateLabel[concept.study_state]}
                              >
                                {concept.title}
                              </NavLink>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </QueryState>
        <NavLink to={`/courses/${courseId}/material`} className="tree-extra">
          All study material
        </NavLink>
        <NavLink to={`/courses/${courseId}/questions`} className="tree-extra">
          Manage questions
        </NavLink>
      </nav>
      <div className="workspace-main">
        <Outlet />
      </div>
    </div>
  );
}
