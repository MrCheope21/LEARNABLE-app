import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { QuickStart } from "../help/QuickStart";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { auth, dashboard, deviceTimezone } from "../../api/endpoints";
import { dashboardKey, FlameIcon, meKey, XpIcon } from "../../app/AppShell";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import type { Translator } from "../../api/client";
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
  const { t } = useI18n();
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <QueryState query={data} label={t("dash.loading")}>
      {(d) => (
        <div className="dashboard">
          <div className="dashboard-main">
            <h1 className="sr-only">{t("dash.title")}</h1>
            <TodayStrip data={d} />
            <QuickStart />
            <TimezoneNote timezone={d.timezone} />
            <NextStepPanel step={d.next_step} />
            <CourseLibrary cards={d.courses} />
          </div>
          <aside className="dashboard-side" aria-label={t("dash.aside")}>
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
  const { t } = useI18n();
  return (
    <div className="today-strip" aria-label={t("dash.today")}>
      <span className="nav-stat">
        <FlameIcon /> {t("community.streakDays", { n: data.streak.current })}
      </span>
      <span className="nav-stat">
        <XpIcon /> {t("dash.xpTodayPlus", { n: data.xp.today })}
      </span>
      <span className="nav-stat">{t("dash.goal", { done: data.goal.done, target: data.goal.target })}</span>
    </div>
  );
}

/** The study day follows the saved timezone; offer the device's when they differ. */
function TimezoneNote({ timezone }: { timezone: string }) {
  const { t } = useI18n();
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
      <span>{t("dash.tzNote", { zone: timezone, device })}</span>
      <button type="button" disabled={save.isPending} onClick={() => save.mutate(device)}>
        {t("dash.tzUse", { zone: device })}
      </button>
      <ErrorBanner error={save.error} />
    </div>
  );
}

export function NextStepPanel({ step }: { step: Schemas["NextStep"] }) {
  const { t } = useI18n();
  const content = nextStepContent(step, t);
  if (!content) return null;
  return (
    <section className={`card next-step${step.kind === "review" ? " review-step" : ""}`} aria-labelledby="next-step-title">
      <div className="next-text">
        <span className="eyebrow title-row">
          {t("next.title")} <HelpTip text="help.nextStep" topic={t("next.title")} guide="review" />
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

function nextStepContent(step: Schemas["NextStep"], t: Translator): { title: string; detail?: string; action: string; to: string | null } | null {
  switch (step.kind) {
    case "resume_consolidation":
      return {
        title: t("next.resumeTitle", { round: step.round ?? 1, total: step.rounds_total ?? 3 }),
        detail: [step.concept_title, step.course_title].filter(Boolean).join(" · ") + (step.count ? ` · ${t("next.answersLeft", { n: step.count })}` : ""),
        action: t("next.resume"),
        to: step.course_id && step.session_id ? `/study/${step.course_id}?session=${step.session_id}` : null,
      };
    case "review":
      return {
        title: t(step.count === 1 ? "review.aria.one" : "review.aria.other", { n: step.count ?? 0 }),
        detail: [step.course_title, t("next.minutes", { n: studyMinutes(step.count ?? 0) })].filter(Boolean).join(" · "),
        action: t("next.startReview"),
        to: step.course_id ? studyLink(step.course_id, "SCHEDULED_REVIEW") : null,
      };
    case "learn":
      return {
        title: t("next.learnTitle", { concept: step.concept_title ?? t("next.nextConcept") }),
        detail: step.course_title ?? undefined,
        action: t("next.learn"),
        to: step.course_id && step.concept_id ? `/courses/${step.course_id}/concepts/${step.concept_id}` : null,
      };
    case "activate":
      return {
        title: t("next.setupTitle", { concept: step.concept_title ?? t("next.theNextConcept") }),
        detail: t("next.setupDetail", { course: step.course_title ?? "" }),
        action: t("next.setup"),
        to: step.course_id && step.concept_id ? `/courses/${step.course_id}/concepts/${step.concept_id}` : null,
      };
    case "setup_course":
      return {
        title: t("next.addMaterialTitle", { course: step.course_title ?? t("next.yourCourse") }),
        detail: t("next.addMaterialDetail"),
        action: t("learn.setup.label"),
        to: step.course_id ? `/courses/${step.course_id}` : null,
      };
    case "create_course":
      return { title: t("next.firstCourse"), detail: t("next.firstCourseDetail"), action: "", to: null };
    case "all_caught_up":
      return { title: t("next.caughtUp"), detail: t("next.caughtUpDetail"), action: "", to: null };
  }
}
