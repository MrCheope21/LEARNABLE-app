import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { studyMinutes } from "../../components/labels";
import { auth } from "../../api/endpoints";
import { dashboardKey, FlameIcon, meKey, XpIcon } from "../../app/AppShell";
import { ErrorBanner } from "../../components/QueryState";

type Dashboard = Schemas["Dashboard"];

// Dates from the server are local calendar days ("2026-09-24"): parsed as UTC midnight and
// formatted in UTC so the day never shifts with the browser's own zone.
const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" });
const longDay = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const monthFormat = new Intl.DateTimeFormat(undefined, { month: "short", timeZone: "UTC" });
const parseDay = (iso: string) => new Date(`${iso}T00:00:00Z`);

export function StreakWidget({ streak }: { streak: Dashboard["streak"] }) {
  const days = streak.current;
  return (
    <section className="card widget" aria-labelledby="streak-title">
      <h2 id="streak-title">Daily streak</h2>
      <p className="big-number">
        <FlameIcon size={30} /> {days} <span className="hint">{days === 1 ? "day" : "days"}</span>
      </p>
      <p className="hint">
        {streak.today_complete
          ? "Today complete. Come back tomorrow to keep it going."
          : days > 0
            ? "Answer one question today to keep your streak."
            : "Answer a question today to start a streak."}
      </p>
      <ol className="week-strip" aria-label="The last 7 days">
        {streak.last_7_days.map((day, index) => (
          <li key={day.date} className={index === streak.last_7_days.length - 1 ? "today" : undefined}>
            {dayFormat.format(parseDay(day.date)).slice(0, 2)}
            <span className={day.active ? "dot on" : "dot"} />
            <span className="sr-only">
              {longDay.format(parseDay(day.date))}: {day.active ? "studied" : "no study"}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ExperienceWidget({ xp }: { xp: Dashboard["xp"] }) {
  return (
    <section className="card widget" aria-labelledby="xp-title">
      <h2 id="xp-title">Experience</h2>
      <p className="big-number">
        <XpIcon size={28} /> {xp.total.toLocaleString()} <span className="hint">XP</span>
      </p>
      <p>
        <strong>+{xp.today.toLocaleString()} XP</strong> today
      </p>
      <details className="hint">
        <summary>How XP works</summary>
        <p>
          Each correct answer to the same learning item earns more: 10 XP the first time, then 20, 30… up to 150. A
          hint halves the XP for that answer. Wrong answers earn nothing but don't reset your progress. XP rewards
          practice; it never changes your review schedule.
        </p>
      </details>
    </section>
  );
}

export function GoalWidget({ goal }: { goal: Dashboard["goal"] }) {
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
      <h2 id="goal-title">Daily goal</h2>
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
      <p className="sr-only">
        Daily goal: {goal.done} of {goal.target} completed answers today, {percent} percent.
      </p>
      <p aria-hidden="true" style={{ textAlign: "center" }}>
        <strong>{goal.done.toLocaleString()}</strong> / {goal.target.toLocaleString()} answers today
      </p>
      {editing ? (
        <form className="goal-form" onSubmit={submit}>
          <label htmlFor={inputId}>
            Answers per day
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
            Save
          </button>
          <button type="button" className="link" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <button type="button" className="link" onClick={() => setEditing(true)}>
          Edit goal
        </button>
      )}
      {!valid && editing && <p className="error">Choose a whole number from 1 to 500.</p>}
      <ErrorBanner error={save.error} />
    </section>
  );
}

const HORIZON_LABEL: Record<Schemas["PlannerHorizon"]["key"], string> = {
  now: "Now",
  "1h": "In 1 hour",
  "4h": "In 4 hours",
  "1d": "In 1 day",
  "3d": "In 3 days",
  "7d": "In 7 days",
};

export function PlannerWidget({ planner }: { planner: Dashboard["planner"] }) {
  return (
    <section className="card widget" aria-labelledby="planner-title">
      <h2 id="planner-title">Time planner</h2>
      {planner.horizons[0]?.key === "now" && planner.horizons[0].items > 0 && (
        <p className="planner-now">
          <strong>{planner.horizons[0].items.toLocaleString()}</strong> due now: about{" "}
          {studyMinutes(planner.horizons[0].items)} min
        </p>
      )}
      <table className="table planner">
        <caption className="sr-only">Reviews due by each time, including overdue ones</caption>
        <thead>
          <tr>
            <th scope="col">Due by</th>
            <th scope="col">Items</th>
          </tr>
        </thead>
        <tbody>
          {planner.horizons.map((h) => (
            <tr key={h.key}>
              <th scope="row">{HORIZON_LABEL[h.key]}</th>
              <td>{h.items.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">Based on your current review schedule; changes as you study. Each row includes everything due before it.</p>
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
  const describe = (c: (typeof cells)[number]) =>
    c.future
      ? `${longDay.format(parseDay(c.date))}: in the future`
      : `${longDay.format(parseDay(c.date))}: ${c.attempts} ${c.attempts === 1 ? "answer" : "answers"}${c.xp ? `, ${c.xp} XP` : ""}`;
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
      <div className="heat-grid" role="group" aria-label={`Activity calendar: ${activeDays} active days, ${total} answers`}>
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
        {shown ? describe(shown) : `${activeDays} active ${activeDays === 1 ? "day" : "days"} · ${total} answers`}
      </p>
      <div className="heat-legend" aria-hidden="true">
        Less
        {[0, 1, 2, 3, 4].map((l) => (
          <span key={l} className={`heat-cell level-${l}`} />
        ))}
        More
        <span className="heat-cell future" style={{ marginLeft: "0.6rem" }} /> Future
      </div>
    </div>
  );
}

export function ActivityWidget({ activity }: { activity: Dashboard["activity"] }) {
  return (
    <section className="card widget" aria-labelledby="activity-title">
      <h2 id="activity-title">Activity</h2>
      <ActivityCalendar activity={activity} />
      <Link to="/activity">See more</Link>
    </section>
  );
}
