import { useMutation, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { useId, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { studyMinutes } from "../../components/labels";
import { auth } from "../../api/endpoints";
import { dashboardKey, FlameIcon, meKey, XpIcon } from "../../app/AppShell";
import { ErrorBanner } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

type Dashboard = Schemas["Dashboard"];

// Dates from the server are local calendar days ("2026-09-24"): parsed as UTC midnight and
// formatted in UTC so the day never shifts with the browser's own zone.
const parseDay = (iso: string) => new Date(`${iso}T00:00:00Z`);

/** Day and month names in the interface language. */
function useDateFormats() {
  const { language } = useI18n();
  return useMemo(
    () => ({
      dayFormat: new Intl.DateTimeFormat(language, { weekday: "short", timeZone: "UTC" }),
      longDay: new Intl.DateTimeFormat(language, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }),
      monthFormat: new Intl.DateTimeFormat(language, { month: "short", timeZone: "UTC" }),
    }),
    [language],
  );
}

export function StreakWidget({ streak }: { streak: Dashboard["streak"] }) {
  const { t } = useI18n();
  const { dayFormat, longDay } = useDateFormats();
  const days = streak.current;
  return (
    <section className="card widget" aria-labelledby="streak-title">
      <div className="title-row">
        <h2 id="streak-title">{t("streak.title")}</h2>
        <HelpTip text="help.streak" topic={t("streak.title")} guide="progress" />
      </div>
      <p className="big-number">
        <FlameIcon size={30} /> {days} <span className="hint">{t(days === 1 ? "streak.unit.one" : "streak.unit.other")}</span>
      </p>
      <p className="hint">
        {streak.today_complete
          ? t("streak.done")
          : days > 0
            ? t("streak.keep")
            : t("streak.start")}
      </p>
      <ol className="week-strip" aria-label={t("streak.last7")}>
        {streak.last_7_days.map((day, index) => (
          <li key={day.date} className={index === streak.last_7_days.length - 1 ? "today" : undefined}>
            {dayFormat.format(parseDay(day.date)).slice(0, 2)}
            <span className={day.active ? "dot on" : "dot"} />
            <span className="sr-only">
              {longDay.format(parseDay(day.date))}: {day.active ? t("streak.studied") : t("streak.noStudy")}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ExperienceWidget({ xp }: { xp: Dashboard["xp"] }) {
  const { t } = useI18n();
  return (
    <section className="card widget" aria-labelledby="xp-title">
      <div className="title-row">
        <h2 id="xp-title">{t("xp.title")}</h2>
        <HelpTip text="help.xp" topic={t("xp.title")} guide="progress" />
      </div>
      <p className="big-number">
        <XpIcon size={28} /> {xp.total.toLocaleString()} <span className="hint">XP</span>
      </p>
      <p>
        <strong>{t("dash.xpTodayPlus", { n: xp.today.toLocaleString() })}</strong>
      </p>
      <p>
        <Link to="/community">🏆 {t("community.seeLeaderboard")}</Link>
      </p>
      <details className="hint">
        <summary>{t("xp.how")}</summary>
        <p>{t("xp.howBody")}</p>
      </details>
    </section>
  );
}

export function GoalWidget({ goal }: { goal: Dashboard["goal"] }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState(String(goal.target));
  const inputId = useId();
  const save = useMutation({
    mutationFn: (value: number) => auth.updateMe({ daily_goal: value }),
    onSuccess: (user) => {
      queryClient.setQueryData(meKey, user);
      void queryClient.invalidateQueries({ queryKey: dashboardKey });
      setEditing(false);
    },
  });
  const share = goal.target > 0 ? Math.min(1, goal.done / goal.target) : 0;
  const percent = goal.target > 0 ? Math.round((goal.done / goal.target) * 100) : 0;
  const parsed = Number(target);
  const valid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 500;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) save.mutate(parsed);
  };

  // A semicircle from 180° to 0°; the fill caps at 100% even when the goal is exceeded.
  const radius = 70;
  const length = Math.PI * radius;
  return (
    <section className="card widget" aria-labelledby="goal-title">
      <div className="title-row">
        <h2 id="goal-title">{t("goal.title")}</h2>
        <HelpTip text="help.goal" topic={t("goal.title")} guide="progress" />
      </div>
      <div className="gauge">
        <svg viewBox="0 0 180 100" aria-hidden="true" focusable="false">
          <path d="M20,90 A70,70 0 0 1 160,90" fill="none" stroke="var(--track)" strokeWidth="14" strokeLinecap="round" />
          <path
            d="M20,90 A70,70 0 0 1 160,90"
            fill="none"
            stroke="var(--brand)"
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={`${length * share} ${length}`}
          />
        </svg>
        <span className="gauge-value">{percent}%</span>
      </div>
      <p className="sr-only">{t("goal.sr", { done: goal.done, target: goal.target, percent })}</p>
      <p aria-hidden="true" style={{ textAlign: "center" }}>
        {t("goal.answersToday", { done: goal.done.toLocaleString(), target: goal.target.toLocaleString() })}
      </p>
      {editing ? (
        <form className="goal-form" onSubmit={submit}>
          <label htmlFor={inputId}>
            {t("goal.perDay")}
            <input
              id={inputId}
              type="number"
              inputMode="numeric"
              min={1}
              max={500}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              aria-invalid={!valid}
            />
          </label>
          <button type="submit" className="primary" disabled={!valid || save.isPending}>
            {t("common.save")}
          </button>
          <button type="button" className="link" onClick={() => setEditing(false)}>
            {t("common.cancel")}
          </button>
        </form>
      ) : (
        <button type="button" className="link" onClick={() => setEditing(true)}>
          {t("goal.edit")}
        </button>
      )}
      {!valid && editing && <p className="error">{t("goal.invalid")}</p>}
      <ErrorBanner error={save.error} />
    </section>
  );
}

export function PlannerWidget({ planner }: { planner: Dashboard["planner"] }) {
  const { t } = useI18n();
  return (
    <section className="card widget" aria-labelledby="planner-title">
      <div className="title-row">
        <h2 id="planner-title">{t("planner.title")}</h2>
        <HelpTip text="help.planner" topic={t("planner.title")} guide="review" />
      </div>
      {planner.horizons[0]?.key === "now" && planner.horizons[0].items > 0 && (
        <p className="planner-now">
          {t("planner.dueNow", { n: planner.horizons[0].items.toLocaleString(), min: studyMinutes(planner.horizons[0].items) })}
        </p>
      )}
      <table className="table planner">
        <caption className="sr-only">{t("planner.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("planner.dueBy")}</th>
            <th scope="col">{t("planner.items")}</th>
          </tr>
        </thead>
        <tbody>
          {planner.horizons.map((h) => (
            <tr key={h.key}>
              <th scope="row">{t(`planner.${h.key}` as MessageKey)}</th>
              <td>{h.items.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">{t("planner.hint")}</p>
    </section>
  );
}

function level(attempts: number): number {
  if (attempts <= 0) return 0;
  if (attempts < 5) return 1;
  if (attempts < 15) return 2;
  if (attempts < 30) return 3;
  return 4;
}

/** Weeks as columns, weekdays as rows (Monday first), from the server's local calendar days. */
export function ActivityCalendar({ activity, large = false }: { activity: Schemas["Activity"]; large?: boolean }) {
  const { t } = useI18n();
  const { longDay, monthFormat } = useDateFormats();
  const [focused, setFocused] = useState<string | null>(null);
  const byDate = useMemo(() => new Map(activity.days.map((d) => [d.date, d])), [activity.days]);
  const cells = useMemo(() => {
    const out: { date: string; attempts: number; xp: number; future: boolean; today: boolean }[] = [];
    const start = parseDay(activity.start);
    const end = parseDay(activity.end);
    for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      const day = byDate.get(iso);
      out.push({ date: iso, attempts: day?.attempts ?? 0, xp: day?.xp ?? 0, future: iso > activity.today, today: iso === activity.today });
    }
    return out;
  }, [activity, byDate]);
  const weeks = Math.ceil(cells.length / 7);
  const months = Array.from({ length: weeks }, (_, w) => {
    const first = cells[w * 7];
    if (!first) return "";
    const date = parseDay(first.date);
    return date.getUTCDate() <= 7 ? monthFormat.format(date) : "";
  });
  const answersText = (n: number) => t(n === 1 ? "unit.answer.one" : "unit.answer.other", { n });
  const describe = (c: (typeof cells)[number]) =>
    c.future
      ? t("activity.future", { day: longDay.format(parseDay(c.date)) })
      : t(c.xp ? "activity.dayXp" : "activity.day", { day: longDay.format(parseDay(c.date)), answers: answersText(c.attempts), xp: c.xp });
  const shown = cells.find((c) => c.date === focused);
  const total = cells.reduce((sum, c) => sum + c.attempts, 0);
  const activeDays = cells.filter((c) => c.attempts > 0).length;

  return (
    <div className={large ? "heatmap large" : "heatmap"}>
      <div className="heat-months" aria-hidden="true">
        {months.map((m, i) => (
          <span key={i}>{m}</span>
        ))}
      </div>
      <div className="heat-grid" role="group" aria-label={t("activity.aria", { days: t(activeDays === 1 ? "unit.activeDay.one" : "unit.activeDay.other", { n: activeDays }), answers: answersText(total) })}>
        {cells.map((c) => (
          <button
            key={c.date}
            type="button"
            className={`heat-cell level-${level(c.attempts)}${c.future ? " future" : ""}${c.today ? " today" : ""}`}
            aria-label={describe(c)}
            title={describe(c)}
            onFocus={() => setFocused(c.date)}
            onMouseEnter={() => setFocused(c.date)}
            onClick={() => setFocused(c.date)}
          />
        ))}
      </div>
      <p className="heat-tip" aria-live="polite">
        {shown ? describe(shown) : t("activity.summary", { days: t(activeDays === 1 ? "unit.activeDay.one" : "unit.activeDay.other", { n: activeDays }), answers: answersText(total) })}
      </p>
      <div className="heat-legend" aria-hidden="true">
        {t("activity.less")}
        {[0, 1, 2, 3, 4].map((l) => (
          <span key={l} className={`heat-cell level-${l}`} />
        ))}
        {t("activity.more")}
        <span className="heat-cell future" style={{ marginLeft: "0.6rem" }} /> {t("activity.legendFuture")}
      </div>
    </div>
  );
}

export function ActivityWidget({ activity }: { activity: Dashboard["activity"] }) {
  const { t } = useI18n();
  return (
    <section className="card widget" aria-labelledby="activity-title">
      <div className="title-row">
        <h2 id="activity-title">{t("activity.title")}</h2>
        <HelpTip text="help.activity" topic={t("activity.title")} guide="progress" />
      </div>
      <ActivityCalendar activity={activity} />
      <Link to="/activity">{t("activity.seeMore")}</Link>
    </section>
  );
}
