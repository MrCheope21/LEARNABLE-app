import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, type Schemas } from "../../api/client";
import { concepts, learningItems, progress, reorder, type ConceptAction } from "../../api/endpoints";
import { EditableTitle } from "../../components/EditableTitle";
import { HelpTip } from "../../components/HelpTip";
import { Tooltip } from "../../components/Tooltip";
import { ReferenceDrawingEditor } from "./ReferenceDrawingEditor";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { MemoryBlock } from "../../components/ProgressBlocks";
import { SortableList } from "../../components/SortableList";
import { dateTime, memoryStateLabel, pageLabel, roleLabel, studyStateLabel } from "../../components/labels";
import { Breadcrumbs, ConsolidatePanel } from "./Consolidate";
import { courseProgressKey, outlineKey, refreshTitles } from "./CourseLayout";

/** Polling interval while the backend generates Learning Items. Exported for tests. */
export const GENERATION_POLL_MS = { value: 1500 };

type Action = { action: ConceptAction; label: string; explains: string; primary?: boolean };

const ACTIVATE: Action = {
  action: "activate",
  label: "Activate",
  explains: "Prepares this concept's questions from your material so you can study it.",
  primary: true,
};
const actionsFor: Record<Schemas["StudyState"], Action[]> = {
  NOT_STUDIED: [
    ACTIVATE,
    { action: "mark-studied", label: "Mark as studied", explains: "You studied it elsewhere: it is noted, without preparing questions yet." },
  ],
  STUDIED: [ACTIVATE],
  COMPLETED: [{ ...ACTIVATE, explains: "Studies it again: its questions come back into your sessions." }],
  ACTIVE: [
    { action: "pause", label: "Pause", explains: "Stops its questions for a while. Nothing is lost." },
    { action: "deactivate", label: "Deactivate", explains: "Takes it out of study and reviews. Your answers and history are kept." },
  ],
  PAUSED: [
    { action: "resume", label: "Resume", explains: "Brings its questions back into study and reviews.", primary: true },
    { action: "deactivate", label: "Deactivate", explains: "Takes it out of study and reviews. Your answers and history are kept." },
  ],
};

/**
 * One Concept: study state, activation, its Learning Items and memory. Activating starts item
 * generation on the backend; this follows it until the items exist. Nothing is activated
 * automatically: the user decides.
 */
export function ConceptPage() {
  const { courseId = "", conceptId = "" } = useParams();
  const queryClient = useQueryClient();
  const concept = useQuery({
    queryKey: ["concept", conceptId],
    queryFn: () => concepts.get(conceptId),
    refetchInterval: (query) =>
      query.state.data?.item_generation_status === "GENERATING" ? GENERATION_POLL_MS.value : false,
  });
  const items = useQuery({ queryKey: ["items", conceptId], queryFn: () => concepts.learningItems(conceptId) });
  const courseProgress = useQuery({ queryKey: courseProgressKey(courseId), queryFn: () => progress.course(courseId) });

  const refreshAround = () => {
    void queryClient.invalidateQueries({ queryKey: ["items", conceptId] });
    void queryClient.invalidateQueries({ queryKey: outlineKey(courseId) });
    void queryClient.invalidateQueries({ queryKey: courseProgressKey(courseId) });
    void queryClient.invalidateQueries({ queryKey: ["home"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["consolidation", conceptId] });
  };

  // When generation finishes, the items (and progress) changed.
  const status = concept.data?.item_generation_status;
  const previous = useRef(status);
  useEffect(() => {
    if (previous.current === "GENERATING" && status !== "GENERATING") refreshAround();
    previous.current = status;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const act = useMutation({
    mutationFn: (action: ConceptAction) => concepts.perform(conceptId, action),
    onSuccess: (updated) => {
      queryClient.setQueryData(["concept", conceptId], updated);
      refreshAround();
    },
  });
  const generate = useMutation({
    mutationFn: () => concepts.generateItems(conceptId),
    onSuccess: (updated) => queryClient.setQueryData(["concept", conceptId], updated),
  });

  const conceptProgress = courseProgress.data?.chapters
    .flatMap((c) => c.topics)
    .flatMap((t) => t.concepts)
    .find((c) => c.id === conceptId);

  return (
    <div className="page">
      <QueryState query={concept}>
        {(data) => {
          return (
            <>
              <Breadcrumbs courseId={courseId} chapterId={data.chapter_id} topicId={data.topic_id} current={data.title} />
              <header className="page-header">
                <EditableTitle
                  title={data.title}
                  description={data.description}
                  label="concept"
                  onSave={async (values) => {
                    const updated = await concepts.update(conceptId, values);
                    queryClient.setQueryData(["concept", conceptId], updated);
                    refreshTitles(queryClient, courseId);
                  }}
                />
                <span className="title-row">
                  <span className={`pill state-${data.study_state.toLowerCase()}`}>{studyStateLabel[data.study_state]}</span>
                  <HelpTip text="help.concept" topic="Concept" guide="study" />
                </span>
              </header>
              {data.needs_source_review && (
                <p className="banner warning">
                  The material this concept came from was deleted. Keep, edit or delete it.
                </p>
              )}
              {/* What to study comes first, then "I have studied it", then managing the concept. */}
              <QueryState query={items} label="Loading learning items…">
                {(list) => (list.length > 0 ? <ItemList items={list} conceptId={conceptId} /> : null)}
              </QueryState>
              <ConsolidatePanel courseId={courseId} conceptId={conceptId} active={data.study_state === "ACTIVE"} />
              <section className="card" aria-label="Manage this concept">
                <div className="actions">
                  {actionsFor[data.study_state].map(({ action, label, explains, primary }) => (
                    <Tooltip key={action} text={explains}>
                      <button
                        type="button"
                        className={primary ? "primary" : undefined}
                        disabled={act.isPending}
                        onClick={() => act.mutate(action)}
                      >
                        {label}
                      </button>
                    </Tooltip>
                  ))}
                </div>
                <ErrorBanner error={act.error} />
                <GenerationStatus
                  concept={data}
                  retrying={generate.isPending}
                  onRetry={() => generate.mutate()}
                  error={generate.error}
                />
              </section>
              {conceptProgress && conceptProgress.memory.items_trained > 0 && (
                <div className="stat-grid">
                  <MemoryBlock memory={conceptProgress.memory} />
                  {conceptProgress.misconceptions.length > 0 && (
                    <section className="stat-block">
                      <h3>Recurring misconceptions</h3>
                      <ul>
                        {conceptProgress.misconceptions.map((m, i) => (
                          <li key={i}>{m}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>
              )}
            </>
          );
        }}
      </QueryState>
    </div>
  );
}

function GenerationStatus({
  concept,
  retrying,
  onRetry,
  error,
}: {
  concept: Schemas["ConceptRead"];
  retrying: boolean;
  onRetry: () => void;
  error: unknown;
}) {
  const status = concept.item_generation_status;
  if (status === "GENERATING") {
    return (
      <p className="banner info" role="status">
        Preparing learning items…
      </p>
    );
  }
  if (status === "FAILED" || status === "INSUFFICIENT_CONTEXT") {
    return (
      <div className="banner warning" role="status">
        <span>{concept.item_generation_error ?? "Learning items couldn't be prepared."}</span>
        <button type="button" disabled={retrying} onClick={onRetry}>
          Try again
        </button>
        {error instanceof ApiError && error.status === 409 && (
          <span> This concept has no source material to build learning items from.</span>
        )}
      </div>
    );
  }
  return null;
}

/** What the concept teaches, readable at once; each item's memory, questions and sources on demand. */
function ItemList({ items, conceptId }: { items: Schemas["LearningItemRead"][]; conceptId: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const queryClient = useQueryClient();
  return (
    <section className="card study-content" aria-labelledby="study-content-title">
      <h2 id="study-content-title">What to study</h2>
      <p className="hint">Read these, then press "I have studied this concept" below to practise them.</p>
      <SortableList
        className="question-list"
        items={items}
        itemLabel={(item) => item.title}
        onReorder={async (ids) => {
          await reorder.learningItems(conceptId, ids);
          void queryClient.invalidateQueries({ queryKey: ["items", conceptId] });
          void queryClient.invalidateQueries({ queryKey: ["course-items"] });
        }}
        renderItem={(item) => (
          <article className="item-entry">
            <h3 className="item-title">{item.title}</h3>
            {item.objective && <p className="hint">{item.objective}</p>}
            <p className="reading">{item.expected_knowledge}</p>
            {item.essential_points.length > 0 && (
              <ul className="key-points">
                {item.essential_points.map((point, index) => (
                  <li key={index}>{point}</li>
                ))}
              </ul>
            )}
            <button
              type="button"
              className="link item-details-toggle"
              aria-expanded={open === item.id}
              onClick={() => setOpen(open === item.id ? null : item.id)}
            >
              {open === item.id ? "Hide details" : "Details"}
              <span className="hint">
                {" "}
                · {roleLabel[item.role]} · {memoryStateLabel[item.review_state.state]}
                {item.review_state.level > 0 && ` · Level ${item.review_state.level}`}
                {item.review_state.marked_hard && " · Marked hard"}
                {!item.in_training && " · Not in training"}
              </span>
            </button>
            {open === item.id && <ItemDetail item={item} conceptId={conceptId} />}
          </article>
        )}
      />
    </section>
  );
}

function ItemDetail({ item, conceptId }: { item: Schemas["LearningItemRead"]; conceptId: string }) {
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["item-sources", item.id], queryFn: () => learningItems.sources(item.id) });
  const training = useMutation({
    mutationFn: (inTraining: boolean) => learningItems.setInTraining(item.id, inTraining),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["items", conceptId] }),
  });
  const memory = item.review_state;
  return (
    <div className="item-detail">
      <dl className="stats compact">
        <div className="stat">
          <dt>State</dt>
          <dd>{memoryStateLabel[memory.state]}</dd>
        </div>
        <div className="stat">
          <dt>Level</dt>
          <dd>{memory.level}</dd>
        </div>
        <div className="stat">
          <dt>Next review</dt>
          <dd>{dateTime(memory.due_at)}</dd>
        </div>
        <div className="stat">
          <dt>Reviews</dt>
          <dd>{memory.review_count}</dd>
        </div>
        <div className="stat">
          <dt>Lapses</dt>
          <dd>{memory.lapse_count}</dd>
        </div>
      </dl>
      <label className="toggle">
        <input
          type="checkbox"
          checked={item.in_training}
          disabled={training.isPending}
          onChange={(e) => training.mutate(e.target.checked)}
        />
        In training
      </label>
      <ReferenceDrawingEditor
        item={item}
        onChanged={() => void queryClient.invalidateQueries({ queryKey: ["items", conceptId] })}
      />
      <h4>Questions</h4>
      <ul>
        {item.questions.map((q) => (
          <li key={q.id}>{q.text}</li>
        ))}
      </ul>
      <h4>Sources</h4>
      <QueryState query={sources} label="Loading sources…">
        {(passages) =>
          passages.length === 0 ? (
            <p className="hint">No source passages.</p>
          ) : (
            <>
              {passages.map((p) => (
                <blockquote key={p.id} className="passage">
                  {(p.page_number != null || p.section) && (
                    <cite>{[pageLabel(p.page_number, p.page_end), p.section].filter(Boolean).join(" · ")}</cite>
                  )}
                  {p.text}
                </blockquote>
              ))}
            </>
          )
        }
      </QueryState>
    </div>
  );
}
