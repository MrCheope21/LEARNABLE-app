import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { courses, study } from "../../api/endpoints";
import { Icon } from "../../components/Icon";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { groupQueue } from "../study/QueuePanel";
import { studyLink } from "../study/StudyPage";

type Item = Schemas["QueueItem"];
type Filter = "all" | "hard" | "late";

/**
 * "Choose what to review": every question that is due, in the order they were added to the course
 * and grouped by chapter and topic. Tick the ones to review now (or a whole group); the review
 * asks them in course order and counts for the schedule like any review.
 */
export function ReviewQueuePage() {
  const { t } = useI18n();
  const { courseId = "" } = useParams();
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const queue = useQuery({ queryKey: ["due-queue", courseId], queryFn: () => study.dueQueue(courseId), gcTime: 0 });
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const shown = useMemo(() => {
    const items = queue.data?.items ?? [];
    const needle = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        (filter === "all" || (filter === "hard" ? item.marked_hard : item.overdue_days >= 1)) &&
        (!needle || `${item.question} ${item.concept_title}`.toLowerCase().includes(needle)),
    );
  }, [queue.data, search, filter]);

  const toggle = (ids: string[], on: boolean) =>
    setPicked((current) => {
      const next = new Set(current);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });

  const order = new Map((queue.data?.items ?? []).map((item, index) => [item.learning_item_id, index + 1]));
  const chosen = (queue.data?.items ?? []).filter((item) => picked.has(item.learning_item_id));
  const total = queue.data?.total ?? 0;

  return (
    <div className="page review-queue">
      <p className="breadcrumbs">
        <Link to="/review">← {t("rq.back")}</Link>
      </p>
      <div className="page-header">
        <h1>{t("rq.title")}</h1>
        <p className="hint">
          {course.data?.title ? `${course.data.title} · ` : ""}
          {t("rq.intro")}
        </p>
      </div>
      <QueryState query={queue}>
        {(data) =>
          data.total === 0 ? (
            <p className="state caught-up" role="status">
              <Icon name="check" size={20} /> {t("rq.none")}
            </p>
          ) : (
            <>
              <div className="queue-tools">
                <input type="search" value={search} placeholder={t("rq.search")} aria-label={t("rq.search")} onChange={(e) => setSearch(e.target.value)} />
                <div className="tabs" role="group" aria-label={t("rq.filter")}>
                  {(["all", "hard", "late"] as Filter[]).map((value) => (
                    <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>
                      {t(`rq.filter.${value}` as "rq.filter.all")}
                    </button>
                  ))}
                </div>
                <button type="button" className="link" onClick={() => toggle(shown.map((i) => i.learning_item_id), true)}>
                  {t("rq.selectAll")}
                </button>
                {picked.size > 0 && (
                  <button type="button" className="link" onClick={() => setPicked(new Set())}>
                    {t("rq.clear")}
                  </button>
                )}
              </div>
              {shown.length === 0 ? (
                <p className="state">{t("rq.noMatch")}</p>
              ) : (
                <div className="queue-groups wide">
                  {groupQueue(shown).map((chapter) => (
                    <section key={chapter.chapter} className="card">
                      <GroupHeader
                        level={2}
                        title={chapter.chapter}
                        items={chapter.topics.flatMap((topic) => topic.items)}
                        picked={picked}
                        onToggle={toggle}
                      />
                      {chapter.topics.map((topic) => (
                        <div key={topic.topic} className="queue-topic">
                          <GroupHeader level={3} title={topic.topic} items={topic.items} picked={picked} onToggle={toggle} />
                          <ul className="queue-list">
                            {topic.items.map((item) => (
                              <QuestionRow key={item.learning_item_id} item={item} number={order.get(item.learning_item_id) ?? 0} checked={picked.has(item.learning_item_id)} onToggle={toggle} />
                            ))}
                          </ul>
                        </div>
                      ))}
                    </section>
                  ))}
                </div>
              )}
              <div className="queue-bar" role="region" aria-label={t("rq.barLabel")}>
                <span>{picked.size > 0 ? t("rq.selected", { n: picked.size }) : t("rq.noneSelected", { n: total })}</span>
                <span className="queue-bar-actions">
                  {picked.size > 0 ? (
                    <Link className="button primary" to={studyLink(courseId, "SCHEDULED_REVIEW", { mode: "SELECTED", itemIds: chosen.map((i) => i.learning_item_id) })}>
                      {t("rq.reviewSelected", { n: picked.size })}
                    </Link>
                  ) : null}
                  <Link className={picked.size > 0 ? "button" : "button primary"} to={studyLink(courseId, "SCHEDULED_REVIEW")}>
                    {t("rq.reviewAll", { n: total })}
                  </Link>
                </span>
              </div>
            </>
          )
        }
      </QueryState>
    </div>
  );
}

function GroupHeader({ level, title, items, picked, onToggle }: { level: 2 | 3; title: string; items: Item[]; picked: Set<string>; onToggle: (ids: string[], on: boolean) => void }) {
  const { t } = useI18n();
  const ids = items.map((i) => i.learning_item_id);
  const count = ids.filter((id) => picked.has(id)).length;
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className={`queue-group-head level-${level}`}>
      <label className="queue-check">
        <input
          type="checkbox"
          checked={count === ids.length}
          ref={(el) => {
            if (el) el.indeterminate = count > 0 && count < ids.length;
          }}
          aria-label={t("rq.selectGroup", { name: title })}
          onChange={(e) => onToggle(ids, e.target.checked)}
        />
      </label>
      <Heading>{title}</Heading>
      <span className="hint">{ids.length}</span>
    </div>
  );
}

function QuestionRow({ item, number, checked, onToggle }: { item: Item; number: number; checked: boolean; onToggle: (ids: string[], on: boolean) => void }) {
  const { t } = useI18n();
  const late = item.overdue_days >= 1 ? t(item.overdue_days === 1 ? "rq.late.one" : "rq.late.other", { n: item.overdue_days }) : t("rq.dueToday");
  return (
    <li>
      <label className={checked ? "queue-row selected" : "queue-row"}>
        <input type="checkbox" checked={checked} onChange={(e) => onToggle([item.learning_item_id], e.target.checked)} />
        <span className="queue-number">{number}</span>
        <span className="queue-question">
          {item.question}
          <span className="queue-concept">{item.concept_title}</span>
        </span>
        <span className="queue-meta">
          {item.marked_hard && <span className="pill">{t("queue.hard")}</span>}
          {late}
        </span>
      </label>
    </li>
  );
}
