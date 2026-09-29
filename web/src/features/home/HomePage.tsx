import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { dashboard } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { QueryState } from "../../components/QueryState";
import { CourseCover, ReviewButton } from "../courses/CourseParts";
import { studyLink } from "../study/StudyPage";

/** Progress per course (GET /home, per-course review load and mastery estimate). */
export const homeKey = ["home"] as const;

/**
 * Review: scheduled review first, per course, with the same due counts as the dashboard.
 * Practising marked-hard questions is a separate, clearly secondary choice (it never changes the
 * schedule unless asked).
 */
export function ReviewHubPage() {
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <div className="page">
      <header className="page-header">
        <h1>Review</h1>
        <p className="hint">Scheduled reviews keep what you've learned. Due counts use the same rules as a review session.</p>
      </header>
      <QueryState query={data}>
        {(d) =>
          d.courses.length === 0 ? (
            <p className="state">
              No courses yet. <Link to="/">Create one on your dashboard</Link>.
            </p>
          ) : (
            <ul className="course-list">
              {[...d.courses]
                .sort((a, b) => b.due_now - a.due_now || a.title.localeCompare(b.title))
                .map((course) => (
                  <li key={course.id}>
                    <article className="card course-card" aria-labelledby={`review-${course.id}`}>
                      <CourseCover id={course.id} title={course.title} to={`/courses/${course.id}`} />
                      <div className="course-body">
                        <Link id={`review-${course.id}`} className="course-title" to={`/courses/${course.id}`}>
                          {course.title}
                        </Link>
                        <span className="metric-label">
                          <b>{course.due_now}</b> due now · {course.items_introduced} of {course.items_trained} items introduced
                        </span>
                      </div>
                      <div className="course-actions">
                        <ReviewButton courseId={course.id} due={course.due_now} />
                        <Link className="button" to={studyLink(course.id, "PRACTICE", { mode: "MARKED_HARD" })}>
                          Practice hard questions
                        </Link>
                      </div>
                    </article>
                  </li>
                ))}
            </ul>
          )
        }
      </QueryState>
    </div>
  );
}
