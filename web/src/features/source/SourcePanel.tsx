import { useQuery } from "@tanstack/react-query";
import type { Schemas } from "../../api/client";
import { documents } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { pageLabel, sourceSummary } from "../../components/labels";

export type SourceRef = Schemas["ProposalSource"];

/**
 * "View source" (docs/PROJECT_SPEC.md §18, §66): the exact passage a Learning Item, question or
 * evaluation relies on. Shows only what the backend provides; nothing is inferred.
 */
export function SourcePanel({ source, onClose }: { source: SourceRef; onClose: () => void }) {
  const passage = useQuery({
    queryKey: ["passage", source.document_id, source.chunk_id],
    queryFn: () => documents.passage(source.document_id, source.chunk_id),
    staleTime: Infinity,
  });

  return (
    <aside className="source-panel" aria-label="Source passage">
      <header>
        <div>
          <h3>{source.document_name}</h3>
          <p className="hint">
            {[pageLabel(source.page_number, source.page_end), source.section].filter(Boolean).join(" · ")}
          </p>
        </div>
        <button type="button" className="link" onClick={onClose} aria-label="Close source">
          Close
        </button>
      </header>
      <QueryState query={passage} label="Loading passage…">
        {(chunk) => <blockquote className="passage">{chunk.text}</blockquote>}
      </QueryState>
    </aside>
  );
}

/** A clickable source line ("banca.pdf · p. 3 · Contratti"). */
export function SourceLink({ source, onOpen }: { source: SourceRef; onOpen: (source: SourceRef) => void }) {
  return (
    <button type="button" className="source-link" onClick={() => onOpen(source)} title="Open the source passage">
      <span aria-hidden="true">📄</span> {sourceSummary(source)}
    </button>
  );
}
