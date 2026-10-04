import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { QuickStart } from "../help/QuickStart";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { auth, dashboard, deviceTimezone } from "../../api/endpoints";
import { dashboardKey, FlameIcon, meKey, XpIcon } from "../../app/AppShell";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { studyMinutes } from "../../components/labels";
import { studyLink } from "../study/StudyPage";
import { CourseLibrary } from "./CourseLibrary";
import { ActivityWidget, ExperienceWidget, GoalWidget, PlannerWidget, StreakWidget } from "./Widgets";

/**
 * The study dashboard (docs/WEB_ARCHITECTURE.md §6): one recommended next step, the course
 * library, and the personal widgets. Every figure comes from GET /dashboard, computed by the
 * server against one timestamp in the user's timezone; nothing is derived here.
 */
export function DashboardPage() {
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <QueryState query={data} label="Loading your dashboard…">
      {(d) => (
        <div className="dashboard">
          <div className="dashboard-main">
            <h1 className="sr-only">Dashboard</h1>
            <TodayStrip data={d} />
            <QuickStart />
            <TimezoneNote timezone={d.timezone} />
            <NextStepPanel step={d.next_step} />
            <CourseLibrary cards={d.courses} />
          </div>
          <aside className="dashboard-side" aria-label="Your study">
            <StreakWidget streak={d.streak} />
            <ExperienceWidget xp={d.xp} />
            <GoalWidget goal={d.goal} />
            <PlannerWidget planner={d.planner} />
            <ActivityWidget activity={d.activity} />
          </aside>
        </div>
      )}
    </QueryState>
  );
}

/** Phones: the day at a glance above the list (the full widgets come after the courses). */
function TodayStrip({ data }: { data: Schemas["Dashboard"] }) {
  return (
    <div className="today-strip" aria-label="Today">
      <span className="nav-stat">
        <FlameIcon /> {data.streak.current} day streak
      </span>
      <span className="nav-stat">
        <XpIcon /> +{data.xp.today} XP today
      </span>
      <span className="nav-stat">
        Goal {data.goal.done}/{data.goal.target}
      </span>
    </div>
  );
}

/** The study day follows the saved timezone; offer the device's when they differ. */
function TimezoneNote({ timezone }: { timezone: string }) {
  const queryClient = useQueryClient();
  const device = deviceTimezone();
  const save = useMutation({
    mutationFn: (tz: string) => auth.updateMe({ timezone: tz }),
    onSuccess: (user) => {
      queryClient.setQueryData(meKey, user);
      void queryClient.invalidateQueries({ queryKey: dashboardKey });
    },
  });
  if (!device || device === timezone) return null;
  return (
    <div className="banner info timezone-note" role="status">
      <span>
        Your study days (streak, goal, XP today) follow <strong>{timezone}</strong>. This device is in <strong>{device}</strong>.
      </span>
      <button type="button" disabled={save.isPending} onClick={() => save.mutate(device)}>
        Use {device}
      </button>
      <ErrorBanner error={save.error} />
    </div>
  );
}

export function NextStepPanel({ step }: { step: Schemas["NextStep"] }) {
  const content = nextStepContent(step);
  if (!content) return null;
  return (
    <section className={`card next-step${step.kind === "review" ? " review-step" : ""}`} aria-labelledby="next-step-title">
      <div className="next-text">
        <span className="eyebrow title-row">
          Your next step <HelpTip text="help.nextStep" topic="Your next step" guide="review" />
        </span>
        <h2 id="next-step-title">{content.title}</h2>
        {content.detail && <span className="hint">{content.detail}</span>}
      </div>
      {content.to && (
        <Link className={`button ${step.kind === "review" ? "review" : "learn"}`} to={content.to}>
          {content.action}
        </Link>
      )}
    </section>
  );
}

function nextStepContent(step: Schemas["NextStep"]): { title: string; detail?: string; action: string; to: string | null } | null {
  switch (step.kind) {
    case "resume_consolidation":
      return {
        title: `Continue consolidation · Round ${step.round ?? 1} of ${step.rounds_total ?? 3}`,
        detail: [step.concept_title, step.course_title].filter(Boolean).join(" · ") + (step.count ? ` · ${step.count} answers left` : ""),
        action: "Resume",
        to: step.course_id && step.session_id ? `/study/${step.course_id}?session=${step.session_id}` : null,
      };
    case "review":
      return {
        title: `Review ${step.count ?? 0} ${step.count === 1 ? "item" : "items"}`,
        detail: [step.course_title, `about ${studyMinutes(step.count ?? 0)} min`].filter(Boolean).join(" · "),
        action: "Start review",
        to: step.course_id ? studyLink(step.course_id, "SCHEDULED_REVIEW") : null,
      };
    case "learn":
      return {
        title: `Continue learning: ${step.concept_title ?? "next concept"}`,
        detail: step.course_title ?? undefined,
        action: "Learn",
        to: step.course_id && step.concept_id ? `/courses/${step.course_id}/concepts/${step.concept_id}` : null,
      };
    case "activate":
      return {
        title: `Set up ${step.concept_title ?? "the next concept"}`,
        detail: `${step.course_title ?? ""} · activate it to prepare its questions`,
        action: "Set up",
        to: step.course_id && step.concept_id ? `/courses/${step.course_id}/concepts/${step.concept_id}` : null,
      };
    case "setup_course":
      return {
        title: `Add material to ${step.course_title ?? "your course"}`,
        detail: "Upload study material or your own questions and answers to build its concepts.",
        action: "Add material",
        to: step.course_id ? `/courses/${step.course_id}` : null,
      };
    case "create_course":
      return { title: "Start your first course", detail: "Create a course, then add material or your own questions.", action: "", to: null };
    case "all_caught_up":
      return { title: "You're all caught up", detail: "Nothing is due and there's no new material waiting.", action: "", to: null };
  }
}
