import { HelpTip } from "./HelpTip";
import type { Schemas } from "../api/client";
import { percent, studyMinutes } from "./labels";

// Curriculum progress and memory progress are always two separate things, never one score
// (docs/PROJECT_SPEC.md §54).

export function CurriculumBlock({ curriculum }: { curriculum: Schemas["CurriculumProgress"] }) {
  return (
    <section className="stat-block" aria-labelledby="curriculum-heading">
      <h3 id="curriculum-heading">Curriculum</h3>
      <p className="hint">How much of the material you have studied and activated.</p>
      <dl className="stats">
        <Stat label="Concepts active" value={`${curriculum.active} of ${curriculum.concepts}`} />
        <Stat label="Studied" value={curriculum.studied} />
        <Stat label="Completed" value={curriculum.completed} />
        <Stat label="Not studied" value={curriculum.not_studied} />
        {curriculum.paused > 0 && <Stat label="Paused" value={curriculum.paused} />}
      </dl>
    </section>
  );
}

export function MemoryBlock({ memory }: { memory: Schemas["MemoryProgress"] }) {
  return (
    <section className="stat-block" aria-labelledby="memory-heading">
      <h3 id="memory-heading">Memory</h3>
      <p className="hint">How well you retain what you train. Mastery is an estimate from your reviews.</p>
      <dl className="stats">
        <Stat label="Mastery (estimate)" value={percent(memory.mastery)} />
        <Stat label="Items in training" value={memory.items_trained} />
        <Stat label="New" value={memory.new} />
        <Stat label="Learning" value={memory.learning} />
        <Stat label="In review" value={memory.review + memory.relearning} />
        <Stat label="Mastered" value={memory.mastered} />
        {memory.marked_hard > 0 && <Stat label="Marked hard" value={memory.marked_hard} />}
      </dl>
    </section>
  );
}

/** New items are learned in consolidation: three rounds each. */
const ROUNDS_PER_NEW_ITEM = 3;

/**
 * One course's time planner: how many questions come due when, and about how long each batch
 * takes, plus the new material still waiting to be learned.
 */
export function ReviewLoadBlock({ load, title = "Time planner" }: { load: Schemas["ReviewLoad"]; title?: string }) {
  const rows: { label: string; items: number; minutes: number; emphasis?: boolean }[] = [
    { label: "Due now", items: load.due_now, minutes: studyMinutes(load.due_now), emphasis: load.due_now > 0 },
    { label: "Later today", items: load.later_today, minutes: studyMinutes(load.later_today) },
    { label: "Tomorrow", items: load.tomorrow, minutes: studyMinutes(load.tomorrow) },
    { label: "Next 7 days", items: load.next_7_days, minutes: studyMinutes(load.next_7_days) },
    {
      label: "New to learn",
      items: load.new_to_learn,
      minutes: studyMinutes(load.new_to_learn * ROUNDS_PER_NEW_ITEM),
    },
  ];
  return (
    <section className="stat-block" aria-labelledby="load-heading">
      <div className="title-row">
        <h3 id="load-heading">{title}</h3>
        <HelpTip text="help.coursePlanner" topic={title} guide="review" />
      </div>
      {load.overdue > 0 && (
        <p className="hint">
          {load.overdue} {load.overdue === 1 ? "question is" : "questions are"} overdue: start with those.
        </p>
      )}
      <table className="table planner course-planner">
        <caption className="sr-only">Questions coming due in this course, and about how long they take</caption>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Questions</th>
            <th scope="col">Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className={row.emphasis ? "emphasis" : undefined}>
              <th scope="row">{row.label}</th>
              <td>{row.items.toLocaleString()}</td>
              <td>{row.items > 0 ? `~${row.minutes} min` : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Stat({ label, value, emphasis = false }: { label: string; value: string | number; emphasis?: boolean }) {
  return (
    <div className={emphasis ? "stat emphasis" : "stat"}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
