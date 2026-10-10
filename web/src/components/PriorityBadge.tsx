import { useMutation } from "@tanstack/react-query";
import { useId } from "react";
import type { Schemas } from "../api/client";
import { learningItems } from "../api/endpoints";
import { useI18n } from "../i18n";
import { useLabels } from "./useLabels";
import { ErrorBanner } from "./QueryState";

/** "Essential" / "Important" / "Extra" next to a question. */
export function PriorityBadge({ priority }: { priority: number }) {
  const { priorityLabel } = useLabels();
  return <span className={`pill priority priority-${priority}`}>{priorityLabel[priority] ?? priorityLabel[2]}</span>;
}

/**
 * Sets a question's priority. In a course from the marketplace it is the user's own (only their
 * filters and labels change; the author's updates never overwrite it), shown next to the
 * author's with a way back to it.
 */
export function PrioritySelect({ item, onSaved }: { item: Schemas["LearningItemRead"]; onSaved: () => void }) {
  const id = useId();
  const { t } = useI18n();
  const { priorityLabel } = useLabels();
  const save = useMutation({ mutationFn: (priority: number) => learningItems.update(item.id, { priority }), onSuccess: onSaved });
  const author = item.origin_priority;
  return (
    <div className="priority-select">
      <label htmlFor={id}>{author != null ? t("priority.yours") : t("priority.label")}</label>
      <select id={id} value={item.priority} disabled={save.isPending} onChange={(e) => save.mutate(Number(e.target.value))}>
        {[1, 2, 3].map((p) => (
          <option key={p} value={p}>
            {priorityLabel[p]}
          </option>
        ))}
      </select>
      {author != null && author !== item.priority && (
        <span className="hint">
          {t("priority.author", { name: priorityLabel[author] ?? "" })} ·{" "}
          <button type="button" className="link" disabled={save.isPending} onClick={() => save.mutate(author)}>
            {t("priority.useAuthor")}
          </button>
        </span>
      )}
      <ErrorBanner error={save.error} />
    </div>
  );
}
