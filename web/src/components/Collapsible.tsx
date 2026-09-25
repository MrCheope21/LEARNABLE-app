import { useState, type ReactNode } from "react";

function read(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function write(key: string, ids: Set<string>) {
  try {
    localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    // Private mode or blocked storage: collapsing still works, it just isn't remembered.
  }
}

/**
 * Which sections are collapsed, remembered per browser under `storageKey` (e.g. one key per
 * course). Everything starts expanded.
 */
export function useCollapsed(storageKey: string) {
  const [state, setState] = useState(() => ({ key: storageKey, ids: read(storageKey) }));
  // Switching to another course reads that course's set; no effect needed.
  const ids = state.key === storageKey ? state.ids : read(storageKey);
  const save = (next: Set<string>) => {
    setState({ key: storageKey, ids: next });
    write(storageKey, next);
  };
  return {
    isCollapsed: (id: string) => ids.has(id),
    toggle: (id: string) => {
      const next = new Set(ids);
      if (!next.delete(id)) next.add(id);
      save(next);
    },
    setAll: (sectionIds: string[], collapsed: boolean) => {
      const next = new Set(ids);
      for (const id of sectionIds) {
        if (collapsed) next.add(id);
        else next.delete(id);
      }
      save(next);
    },
  };
}

/** The chevron that collapses or expands the section with id `controls`. */
export function CollapseToggle({
  expanded,
  onToggle,
  label,
  controls,
}: {
  expanded: boolean;
  onToggle: () => void;
  label: string;
  controls: string;
}) {
  return (
    <button
      type="button"
      className={expanded ? "collapse-toggle expanded" : "collapse-toggle"}
      aria-expanded={expanded}
      aria-controls={controls}
      aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`}
      onClick={onToggle}
    >
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

/**
 * A heading with a collapse chevron, over a body that hides when collapsed. The body stays
 * mounted (only `hidden`), so an open editor or a drag list keeps its state.
 */
export function CollapsibleSection({
  id,
  label,
  expanded,
  onToggle,
  heading,
  collapsedSummary,
  className,
  as: Tag = "div",
  labelledBy,
  children,
}: {
  id: string;
  label: string;
  expanded: boolean;
  onToggle: () => void;
  heading: ReactNode;
  /** Shown next to the heading while collapsed, e.g. "3 questions". */
  collapsedSummary?: ReactNode;
  className?: string;
  as?: "div" | "section";
  labelledBy?: string;
  children: ReactNode;
}) {
  const bodyId = `section-body-${id}`;
  return (
    <Tag className={className} aria-labelledby={labelledBy}>
      <div className="section-heading">
        <CollapseToggle expanded={expanded} onToggle={onToggle} label={label} controls={bodyId} />
        {heading}
        {!expanded && collapsedSummary}
      </div>
      <div id={bodyId} hidden={!expanded}>
        {children}
      </div>
    </Tag>
  );
}
