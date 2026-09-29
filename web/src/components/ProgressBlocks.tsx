import type { Schemas } from "../api/client";
import { percent } from "./labels";

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

export function ReviewLoadBlock({ load, title = "Upcoming reviews" }: { load: Schemas["ReviewLoad"]; title?: string }) {
  return (
    <section className="stat-block" aria-labelledby="load-heading">
      <h3 id="load-heading">{title}</h3>
      <dl className="stats">
        <Stat label="Due now" value={load.due_now} emphasis={load.due_now > 0} />
        {load.overdue > 0 && <Stat label="Overdue" value={load.overdue} emphasis />}
        <Stat label="Later today" value={load.later_today} />
        <Stat label="Tomorrow" value={load.tomorrow} />
        <Stat label="Next 7 days" value={load.next_7_days} />
        <Stat label="New to learn" value={load.new_to_learn} />
      </dl>
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
