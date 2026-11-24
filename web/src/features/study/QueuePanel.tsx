import { useQuery } from "@tanstack/react-query";
import { study } from "../../api/endpoints";
import type { Schemas } from "../../api/client";
import { QueryState } from "../../components/QueryState";
import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n";

type Item = Schemas["QueueItem"];

/** Questions grouped by chapter and topic, keeping the order they were added to the course. */
export function groupQueue(items: Item[]): { chapter: string; topics: { topic: string; items: Item[] }[] }[] {
  const chapters: { chapter: string; topics: { topic: string; items: Item[] }[] }[] = [];
  for (const item of items) {
    let chapter = chapters.find((c) => c.chapter === item.chapter_title);
    if (!chapter) chapters.push((chapter = { chapter: item.chapter_title, topics: [] }));
    let topic = chapter.topics.find((t) => t.topic === item.topic_title);
    if (!topic) chapter.topics.push((topic = { topic: item.topic_title, items: [] }));
    topic.items.push(item);
  }
  return chapters;
}

/**
 * During a review: the questions still to come, to choose which one is next. The question that
 * was next moves back a slot; nothing is dropped.
 */
export function QueuePanel({
  sessionId,
  onPick,
  onClose,
  working,
}: {
  sessionId: string;
  onPick: (learningItemId: string) => void;
  onClose: () => void;
  working: boolean;
}) {
  const { t } = useI18n();
  const queue = useQuery({ queryKey: ["session-queue", sessionId], queryFn: () => study.queue(sessionId), gcTime: 0 });
  return (
    <aside className="source-panel queue-panel" aria-label={t("queue.title")}>
      <header>
        <div>
          <span className="eyebrow">{t("queue.title")}</span>
          <h3>{t("queue.pick")}</h3>
        </div>
        <button type="button" className="link" onClick={onClose} aria-label={t("conceptPanel.closeAria")}>
          {t("common.close")}
        </button>
      </header>
      <QueryState query={queue}>
        {(data) => (
          <div className="queue-groups">
            {groupQueue(data.items).map((chapter) => (
              <section key={chapter.chapter}>
                <h4>{chapter.chapter}</h4>
                {chapter.topics.map((topic) => (
                  <div key={topic.topic}>
                    <span className="eyebrow">{topic.topic}</span>
                    <ul className="queue-list">
                      {topic.items.map((item) => (
                        <li key={item.learning_item_id}>
                          <button
                            type="button"
                            className={item.current ? "queue-row current" : "queue-row"}
                            disabled={working || item.current}
                            aria-current={item.current ? "true" : undefined}
                            onClick={() => onPick(item.learning_item_id)}
                          >
                            <span className="queue-question">{item.question}</span>
                            <span className="queue-meta">
                              {item.current ? <Icon name="check" size={14} /> : null}
                              {item.current ? t("queue.now") : item.marked_hard ? t("queue.hard") : ""}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            ))}
          </div>
        )}
      </QueryState>
    </aside>
  );
}
