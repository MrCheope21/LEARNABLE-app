import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ErrorBanner } from "./QueryState";

type Props<T extends { id: string }> = {
  items: T[];
  /** Names an item for the drag handle and screen-reader announcements, e.g. its title. */
  itemLabel: (item: T) => string;
  /** Saves the new order (every id once); the caller refetches on success. */
  onReorder: (ids: string[]) => Promise<unknown>;
  renderItem: (item: T) => ReactNode;
  /** Shown instead of the handles, e.g. while a search hides part of the list. */
  disabledReason?: string;
  className?: string;
};

/**
 * A list reordered by drag and drop (mouse, touch, or keyboard: focus a handle, Space, arrows,
 * Space). The new order shows at once and is saved in the background; if saving fails the list
 * returns to the server's order and the error is shown.
 */
export function SortableList<T extends { id: string }>({
  items,
  itemLabel,
  onReorder,
  renderItem,
  disabledReason,
  className = "",
}: Props<T>) {
  // The optimistic order, tied to the `items` it was made from: once the refetch delivers a new
  // list (or the save fails), the server's order shows again. No effect needed to reset it.
  const [pending, setPending] = useState<{ base: T[]; order: T[] } | null>(null);
  const shown = pending && pending.base === items ? pending.order : items;
  const save = useMutation({
    mutationFn: (order: T[]) => onReorder(order.map((item) => item.id)),
    onError: () => setPending(null),
  });
  const sensors = useSensors(
    // A few pixels of movement before a drag starts, so a tap on the handle isn't a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const labelOf = (id: UniqueIdentifier) => {
    const item = shown.find((i) => i.id === id);
    return item ? itemLabel(item) : "Item";
  };
  const positionOf = (id: UniqueIdentifier) => shown.findIndex((i) => i.id === id) + 1;
  const announcements: Announcements = {
    onDragStart: ({ active }) => `Picked up ${labelOf(active.id)}, position ${positionOf(active.id)} of ${shown.length}.`,
    onDragOver: ({ active, over }) =>
      over ? `${labelOf(active.id)} is now at position ${positionOf(over.id)} of ${shown.length}.` : undefined,
    onDragEnd: ({ active, over }) =>
      over ? `${labelOf(active.id)} dropped at position ${positionOf(over.id)} of ${shown.length}.` : `${labelOf(active.id)} dropped.`,
    onDragCancel: ({ active }) => `Moving ${labelOf(active.id)} cancelled.`,
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const order = arrayMove(shown, positionOf(active.id) - 1, positionOf(over.id) - 1);
    setPending({ base: items, order });
    save.mutate(order);
  };

  const sortable = !disabledReason && shown.length > 1;
  return (
    <>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd} accessibility={{ announcements }}>
        <SortableContext items={shown} strategy={verticalListSortingStrategy} disabled={!sortable}>
          <ul className={`sortable-list ${className}`.trim()}>
            {shown.map((item) => (
              <SortableRow key={item.id} id={item.id} label={itemLabel(item)} sortable={sortable}>
                {renderItem(item)}
              </SortableRow>
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      {disabledReason && shown.length > 1 && <p className="hint">{disabledReason}</p>}
      <ErrorBanner error={save.error} />
    </>
  );
}

function SortableRow({ id, label, sortable, children }: { id: string; label: string; sortable: boolean; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      className={isDragging ? "sortable-row dragging" : "sortable-row"}
      style={{ transform: CSS.Translate.toString(transform), transition }}
    >
      {sortable && (
        <button
          type="button"
          ref={setActivatorNodeRef}
          className="drag-handle"
          aria-label={`Reorder ${label}`}
          {...attributes}
          {...listeners}
        >
          <svg viewBox="0 0 12 18" width="12" height="18" aria-hidden="true" focusable="false">
            {[3, 9].flatMap((x) => [3, 9, 15].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.6" fill="currentColor" />))}
          </svg>
        </button>
      )}
      <div className="sortable-content">{children}</div>
    </li>
  );
}
