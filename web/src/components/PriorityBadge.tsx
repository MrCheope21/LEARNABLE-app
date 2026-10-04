import { priorityLabel } from "./labels";

/** "Essential" / "Important" / "Extra" next to a question. */
export function PriorityBadge({ priority }: { priority: number }) {
  return <span className={`pill priority priority-${priority}`}>{priorityLabel[priority] ?? "Important"}</span>;
}
