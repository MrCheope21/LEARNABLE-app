import type { CSSProperties } from "react";
import { HelpTip } from "./HelpTip";
import { Icon } from "./Icon";
import type { Schemas } from "../api/client";
import { useI18n } from "../i18n";
import { percent, studyMinutes } from "./labels";
import { useLabels } from "./useLabels";

// Curriculum progress and memory progress are always two separate things, never one score
// (docs/PROJECT_SPEC.md §54).

export function CurriculumBlock({ curriculum }: { curriculum: Schemas["CurriculumProgress"] }) {
  const { t } = useI18n();
  const { studyStateLabel } = useLabels();
  return (
    <section className="stat-block" aria-labelledby="curriculum-heading">
      <h3 id="curriculum-heading">{t("course.curriculum")}</h3>
      <p className="hint">{t("pb.curriculumHint")}</p>
      {curriculum.concepts > 0 && (
        <div
          className="bar bar-tall"
          role="progressbar"
          aria-label={t("pb.conceptsActive")}
          aria-valuemin={0}
          aria-valuemax={curriculum.concepts}
          aria-valuenow={curriculum.active}
        >
          <span style={{ width: `${Math.round((curriculum.active / curriculum.concepts) * 100)}%` }} />
        </div>
      )}
      <dl className="stats">
        <Stat label={t("pb.conceptsActive")} value={t("pb.activeOf", { active: curriculum.active, total: curriculum.concepts })} />
        <Stat label={studyStateLabel.STUDIED} value={curriculum.studied} />
        <Stat label={studyStateLabel.COMPLETED} value={curriculum.completed} />
        <Stat label={studyStateLabel.NOT_STUDIED} value={curriculum.not_studied} />
        {curriculum.paused > 0 && <Stat label={studyStateLabel.PAUSED} value={curriculum.paused} />}
      </dl>
    </section>
  );
}

export function MemoryBlock({ memory }: { memory: Schemas["MemoryProgress"] }) {
  const { t } = useI18n();
  const { memoryStateLabel } = useLabels();
  return (
    <section className="stat-block" aria-labelledby="memory-heading">
      <h3 id="memory-heading">{t("pb.memory")}</h3>
      <p className="hint">{t("pb.memoryHint")}</p>
      <div className="ring-row">
        <div className="ring" style={{ "--p": `${Math.round((memory.mastery ?? 0) * 100)}%` } as CSSProperties} aria-hidden="true">
          <span>{percent(memory.mastery)}</span>
        </div>
        <StateBar
          parts={[
            { key: "new", n: memory.new, label: memoryStateLabel.NEW },
            { key: "learning", n: memory.learning, label: memoryStateLabel.LEARNING },
            { key: "review", n: memory.review + memory.relearning, label: memoryStateLabel.REVIEW },
            { key: "mastered", n: memory.mastered, label: memoryStateLabel.MASTERED },
          ]}
        />
      </div>
      <dl className="stats">
        <Stat label={t("pb.mastery")} value={percent(memory.mastery)} />
        <Stat label={t("pb.itemsTrained")} value={memory.items_trained} />
        <Stat label={memoryStateLabel.NEW} value={memory.new} />
        <Stat label={memoryStateLabel.LEARNING} value={memory.learning} />
        <Stat label={memoryStateLabel.REVIEW} value={memory.review + memory.relearning} />
        <Stat label={memoryStateLabel.MASTERED} value={memory.mastered} />
        {memory.marked_hard > 0 && <Stat label={t("pb.markedHard")} value={memory.marked_hard} />}
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
export function ReviewLoadBlock({ load, title }: { load: Schemas["ReviewLoad"]; title?: string }) {
  const { t } = useI18n();
  const heading = title ?? t("planner.title");
  const rows: { label: string; items: number; minutes: number; emphasis?: boolean }[] = [
    { label: t("pb.dueNow"), items: load.due_now, minutes: studyMinutes(load.due_now), emphasis: load.due_now > 0 },
    { label: t("pb.laterToday"), items: load.later_today, minutes: studyMinutes(load.later_today) },
    { label: t("pb.tomorrow"), items: load.tomorrow, minutes: studyMinutes(load.tomorrow) },
    { label: t("pb.next7"), items: load.next_7_days, minutes: studyMinutes(load.next_7_days) },
    {
      label: t("pb.newToLearn"),
      items: load.new_to_learn,
      minutes: studyMinutes(load.new_to_learn * ROUNDS_PER_NEW_ITEM),
    },
  ];
  return (
    <section className="stat-block" aria-labelledby="load-heading">
      <div className="title-row">
        <h3 id="load-heading">{heading}</h3>
        <HelpTip text="help.coursePlanner" topic={heading} guide="review" />
      </div>
      {load.overdue > 0 && (
        <p className="hint">{t(load.overdue === 1 ? "pb.overdue.one" : "pb.overdue.other", { n: load.overdue })}</p>
      )}
      {rows.every((row) => row.items === 0) ? (
        <p className="planner-clear">
          <Icon name="check" size={18} /> {t("planner.allClear")}
        </p>
      ) : (
      <table className="table planner course-planner">
        <caption className="sr-only">{t("pb.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("pb.when")}</th>
            <th scope="col">{t("pb.questions")}</th>
            <th scope="col">{t("pb.time")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className={row.emphasis ? "emphasis" : undefined}>
              <th scope="row">{row.label}</th>
              <td>{row.items.toLocaleString()}</td>
              <td>{row.items > 0 ? t("pb.minutes", { n: row.minutes }) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
    </section>
  );
}

/** A single stacked bar for how the trained questions divide into memory states. */
function StateBar({ parts }: { parts: { key: string; n: number; label: string }[] }) {
  const total = parts.reduce((sum, part) => sum + part.n, 0);
  if (total === 0) return null;
  return (
    <div className="state-bar" aria-hidden="true">
      <div className="state-bar-track">
        {parts
          .filter((part) => part.n > 0)
          .map((part) => (
            <span key={part.key} className={`seg seg-${part.key}`} style={{ flexGrow: part.n }} title={`${part.label}: ${part.n}`} />
          ))}
      </div>
    </div>
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
