import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { dashboard } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { Icon } from "../../components/Icon";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
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
  const { t } = useI18n();
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <div className="page">
      <div className="page-header">
        <h1>{t("nav.review")}</h1>
        <p className="hint">{t("home.intro")}</p>
      </div>
      <QueryState query={data}>
        {(d) => {
          if (d.courses.length === 0) {
            return (
              <p className="state">
                {t("home.noCourses")} <Link to="/">{t("home.createOnDashboard")}</Link>.
              </p>
            );
          }
          const sorted = [...d.courses].sort((a, b) => b.due_now - a.due_now || a.title.localeCompare(b.title));
          const due = sorted.filter((course) => course.due_now > 0);
          const rest = sorted.filter((course) => course.due_now <= 0);
          return (
            <>
              {due.length === 0 && (
                <p className="state caught-up" role="status">
                  <Icon name="check" size={20} /> {t("review.allClear")}
                </p>
              )}
              {due.length > 0 && (
                <ul className="course-list">
                  {due.map((course) => (
                    <li key={course.id}>
                      <ReviewCard course={course} />
                    </li>
                  ))}
                </ul>
              )}
              {rest.length > 0 && (
                <details className="other-courses" open={due.length === 0}>
                  <summary>{t(due.length === 0 ? "review.practiceCourses" : "review.otherCourses", { n: rest.length })}</summary>
                  <ul className="course-list">
                    {rest.map((course) => (
                      <li key={course.id}>
                        <ReviewCard course={course} />
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          );
        }}
      </QueryState>
    </div>
  );
}

function ReviewCard({ course }: { course: Schemas["CourseCard"] }) {
  const { t } = useI18n();
  return (
    <article className="card course-card" aria-labelledby={`review-${course.id}`}>
      <CourseCover id={course.id} title={course.title} to={`/courses/${course.id}`} />
      <div className="course-body">
        <Link id={`review-${course.id}`} className="course-title" to={`/courses/${course.id}`}>
          {course.title}
        </Link>
        <span className="metric-label">
          {t("home.meta", { due: course.due_now, introduced: course.items_introduced, trained: course.items_trained })}
        </span>
      </div>
      <div className="course-actions">
        <ReviewButton courseId={course.id} due={course.due_now} />
        <Link className="button" to={studyLink(course.id, "PRACTICE", { mode: "MARKED_HARD" })}>
          {t("course.practiceHard")}
        </Link>
      </div>
    </article>
  );
}
