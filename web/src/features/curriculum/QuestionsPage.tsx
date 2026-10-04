import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { courses, learningItems, reorder } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { CollapsibleSection, useCollapsed } from "../../components/Collapsible";
import { HelpTip } from "../../components/HelpTip";
import { SortableList } from "../../components/SortableList";
import { memoryStateLabel } from "../../components/labels";
import { Breadcrumbs } from "./Consolidate";
import { removalFor, type Removal } from "./selection";
import { courseProgressKey, outlineKey } from "./CourseLayout";

type Item = Schemas["LearningItemRead"];
type Chapter = Schemas["ChapterOutline"];

export const courseItemsKey = (courseId: string) => ["course-items", courseId] as const;

/**
 * Every question of a Course in one place: select one or many, then delete, pause, resume or
 * move them (into a concept, or into a topic where each keeps its own concept); edit one
 * inline. The server applies bulk actions all or nothing.
 */
export function QuestionsPage() {
  const { courseId = "" } = useParams();
  const queryClient = useQueryClient();
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const items = useQuery({ queryKey: courseItemsKey(courseId), queryFn: () => learningItems.listForCourse(courseId) });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const searchId = useId();
  const sections = useCollapsed(`learnable.questions-collapsed.${courseId}`);
  // Search results are never hidden inside a collapsed section.
  const open = (id: string) => Boolean(filter.trim()) || !sections.isCollapsed(id);
  const sectionIds = (outline.data ?? []).flatMap((c) => [c.id, ...c.topics.flatMap((t) => [t.id, ...t.concepts.map((k) => k.id)])]);

  const refresh = () => {
    for (const key of [courseItemsKey(courseId), outlineKey(courseId), courseProgressKey(courseId), ["dashboard"], ["course-summary", courseId], ["items"], ["consolidation"]]) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const bulk = useMutation({
    mutationFn: (body: Schemas["BulkItemAction"]) => learningItems.bulk(courseId, body),
    onSuccess: (result, body) => {
      const verb = { delete: "Deleted", pause: "Paused", resume: "Resumed", move: "Moved" }[body.action];
      const extra = [
        result.created_concepts ? `${result.created_concepts} new ${result.created_concepts === 1 ? "concept" : "concepts"}` : null,
        result.deleted_concepts ? `${result.deleted_concepts} empty ${result.deleted_concepts === 1 ? "concept" : "concepts"} removed` : null,
      ].filter(Boolean);
      setNotice(`${verb} ${result.affected} ${result.affected === 1 ? "question" : "questions"}${extra.length ? ` · ${extra.join(" · ")}` : ""}.`);
      setSelected(new Set());
      setMoving(false);
      refresh();
    },
  });

  const remove = useMutation({
    mutationFn: ({ removal }: { removal: Removal; questions: number }) =>
      courses.deleteCurriculum(courseId, {
        chapter_ids: removal.chapterIds,
        topic_ids: removal.topicIds,
        concept_ids: removal.conceptIds,
        item_ids: removal.itemIds,
      }),
    onSuccess: (_result, { removal, questions }) => {
      const groups = removal.chapterIds.length + removal.topicIds.length + removal.conceptIds.length;
      setNotice(
        `Deleted ${questions} ${questions === 1 ? "question" : "questions"}${groups ? ` and ${groups} emptied ${groups === 1 ? "group" : "groups"}` : ""}.`,
      );
      setSelected(new Set());
      setMoving(false);
      refresh();
    },
  });

  const visible = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    const all = items.data ?? [];
    if (!needle) return all;
    return all.filter(
      (item) =>
        item.title.toLocaleLowerCase().includes(needle) ||
        item.expected_knowledge.toLocaleLowerCase().includes(needle) ||
        item.questions.some((q) => q.text.toLocaleLowerCase().includes(needle)),
    );
  }, [items.data, filter]);

  const toggle = (ids: string[], on: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });

  const ids = [...selected];
  const allVisibleSelected = visible.length > 0 && visible.every((i) => selected.has(i.id));
  const confirmDelete = () => {
    const removal = removalFor(outline.data ?? [], items.data ?? [], selected);
    const count = ids.length;
    const groups = [
      [removal.chapterIds.length, "chapter"],
      [removal.topicIds.length, "topic"],
      [removal.conceptIds.length, "concept"],
    ]
      .filter(([n]) => Number(n) > 0)
      .map(([n, word]) => `${n} ${word}${n === 1 ? "" : "s"}`);
    const also = groups.length ? ` The ${groups.join(", ")} left with no questions are deleted too.` : "";
    if (window.confirm(`Delete ${count} ${count === 1 ? "question" : "questions"}? Their answers and review history are deleted too.${also}`)) {
      remove.mutate({ removal, questions: count });
    }
  };

  return (
    <div className="page questions-page">
      <Breadcrumbs courseId={courseId} current="Questions" />
      <header className="page-header">
        <div className="title-row">
          <h1>Questions</h1>
          <HelpTip text="help.questions" topic="Questions" guide="organise" />
        </div>
        <p className="hint">Select questions to delete, pause, resume or move them; drag ⠿ to reorder them; edit one to fix its title, wording or expected answer.</p>
      </header>

      <div className="toolbar">
        <label className="sr-only" htmlFor={searchId}>
          Search questions
        </label>
        <input id={searchId} type="search" placeholder="Search questions and answers" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button type="button" disabled={visible.length === 0} onClick={() => toggle(visible.map((i) => i.id), !allVisibleSelected)}>
          {allVisibleSelected ? "Deselect all" : `Select all${filter.trim() ? " shown" : ""} (${visible.length})`}
        </button>
        <button type="button" className="link" disabled={Boolean(filter.trim())} onClick={() => sections.setAll(sectionIds, true)}>
          Collapse all
        </button>
        <button type="button" className="link" disabled={Boolean(filter.trim())} onClick={() => sections.setAll(sectionIds, false)}>
          Expand all
        </button>
      </div>

      {selected.size > 0 && (
        <div className="bulk-bar" role="toolbar" aria-label="Selected questions">
          <strong>{selected.size} selected</strong>
          <button type="button" className="primary" aria-expanded={moving} onClick={() => setMoving((v) => !v)}>
            Move to…
          </button>
          <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate({ item_ids: ids, action: "pause", delete_emptied_concepts: false })}>
            Pause
          </button>
          <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate({ item_ids: ids, action: "resume", delete_emptied_concepts: false })}>
            Resume
          </button>
          <button type="button" className="danger" disabled={bulk.isPending || remove.isPending} onClick={confirmDelete}>
            Delete
          </button>
          <button type="button" className="link" onClick={() => setSelected(new Set())}>
            Clear selection
          </button>
        </div>
      )}
      {moving && outline.data && selected.size > 0 && (
        <MoveForm chapters={outline.data} count={selected.size} busy={bulk.isPending} onMove={(target) => bulk.mutate({ item_ids: ids, action: "move", ...target })} onCancel={() => setMoving(false)} />
      )}
      {notice && (
        <p className="banner info" role="status">
          {notice}
          <button type="button" className="link" onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </p>
      )}
      <ErrorBanner error={bulk.error ?? remove.error} />

      <QueryState query={outline}>
        {(chapters) => (
          <QueryState query={items}>
            {() => {
              const byConcept = new Map<string, Item[]>();
              for (const item of visible) byConcept.set(item.concept_id, [...(byConcept.get(item.concept_id) ?? []), item]);
              const anything = chapters.some((c) => c.topics.some((t) => t.concepts.some((k) => byConcept.has(k.id))));
              if (!anything) {
                return <p className="state">{filter ? "No question matches this search." : "No questions yet. Activate a concept or import your own questions and answers."}</p>;
              }
              const idsIn = (concepts: { id: string }[]) => concepts.flatMap((k) => (byConcept.get(k.id) ?? []).map((i) => i.id));
              const section = (id: string, label: string) => ({ id, label, expanded: open(id), onToggle: () => sections.toggle(id) });
              const questionList = (conceptId: string, conceptItems: Item[]) => (
                <SortableList
                  className="question-list"
                  items={conceptItems}
                  itemLabel={(item) => item.questions[0]?.text ?? item.title}
                  disabledReason={filter.trim() ? "Clear the search to reorder these questions." : undefined}
                  onReorder={async (ids) => {
                    await reorder.learningItems(conceptId, ids);
                    refresh();
                  }}
                  renderItem={(item) => (
                    <QuestionRow
                      item={item}
                      selected={selected.has(item.id)}
                      onSelect={(on) => toggle([item.id], on)}
                      editing={editing === item.id}
                      onEdit={() => setEditing(editing === item.id ? null : item.id)}
                      onSaved={() => {
                        setEditing(null);
                        refresh();
                      }}
                    />
                  )}
                />
              );
              return chapters.map((chapter) => {
                const topics = chapter.topics.filter((t) => t.concepts.some((k) => byConcept.has(k.id)));
                if (topics.length === 0) return null;
                return (
                  <CollapsibleSection
                    key={chapter.id}
                    {...section(chapter.id, chapter.title)}
                    as="section"
                    className="card question-group"
                    labelledBy={`qc-${chapter.id}`}
                    heading={
                      <>
                        <GroupCheckbox label={chapter.title} ids={idsIn(topics.flatMap((t) => t.concepts))} selected={selected} onToggle={toggle} />
                        <h2 id={`qc-${chapter.id}`}>{chapter.title}</h2>
                      </>
                    }
                  >
                    {topics.map((topic) => (
                      <CollapsibleSection key={topic.id} {...section(topic.id, topic.title)} className="question-topic" heading={
                          <>
                            <GroupCheckbox label={topic.title} ids={idsIn(topic.concepts)} selected={selected} onToggle={toggle} />
                            <h3>{topic.title}</h3>
                          </>
                        }>
                        {topic.concepts
                          .filter((k) => byConcept.has(k.id))
                          .map((concept) => {
                            const conceptItems = byConcept.get(concept.id) ?? [];
                            return (
                              <CollapsibleSection
                                key={concept.id}
                                {...section(concept.id, concept.title)}
                                className="question-concept"
                                heading={
                                  <>
                                    <GroupCheckbox label={concept.title} ids={idsIn([concept])} selected={selected} onToggle={toggle} />
                                    <Link to={`/courses/${courseId}/concepts/${concept.id}`}>{concept.title}</Link>
                                  </>
                                }
                                collapsedSummary={
                                  <span className="hint">
                                    {conceptItems.length} {conceptItems.length === 1 ? "question" : "questions"}
                                  </span>
                                }
                              >
                                {questionList(concept.id, conceptItems)}
                              </CollapsibleSection>
                            );
                          })}
                      </CollapsibleSection>
                    ))}
                  </CollapsibleSection>
                );
              });
            }}
          </QueryState>
        )}
      </QueryState>
    </div>
  );
}

function QuestionRow({
  item,
  selected,
  onSelect,
  editing,
  onEdit,
  onSaved,
}: {
  item: Item;
  selected: boolean;
  onSelect: (on: boolean) => void;
  editing: boolean;
  onEdit: () => void;
  onSaved: () => void;
}) {
  const first = item.questions[0]?.text ?? item.title;
  const others = item.questions.length - 1;
  return (
    <div className={selected ? "question-row selected" : "question-row"}>
      <input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} aria-label={`Select: ${first}`} />
      <div className="question-text">
        <span>{first}</span>
        <span className="hint">
          {others > 0 && `+${others} ${others === 1 ? "other wording" : "other wordings"} · `}
          {memoryStateLabel[item.review_state.state]}
          {item.paused && " · Paused"}
          {!item.in_training && " · Not in training"}
        </span>
      </div>
      <button type="button" className="link" aria-expanded={editing} onClick={onEdit}>
        {editing ? "Close" : "Edit"}
      </button>
      {editing && <ItemEditor item={item} onSaved={onSaved} />}
    </div>
  );
}

/** Edits the item's title, wordings, expected answer and key points. Memory state is kept. */
function ItemEditor({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const [title, setTitle] = useState(item.title);
  const [wordings, setWordings] = useState(item.questions.map((q) => ({ id: q.id as string | null, text: q.text })));
  const [removed, setRemoved] = useState<string[]>([]);
  const [answer, setAnswer] = useState(item.expected_knowledge);
  const [points, setPoints] = useState(item.essential_points.join("\n"));
  const save = useMutation({
    mutationFn: async () => {
      const keyPoints = points
        .split("\n")
        .map((p) => p.trim())
        .filter(Boolean)
        .slice(0, 10);
      await learningItems.update(item.id, { title: title.trim(), expected_knowledge: answer, essential_points: keyPoints });
      for (const id of removed) await learningItems.deleteQuestion(id);
      for (const wording of wordings) {
        const text = wording.text.trim();
        if (!text) continue;
        if (wording.id === null) await learningItems.addQuestion(item.id, text);
        else if (text !== item.questions.find((q) => q.id === wording.id)?.text) await learningItems.updateQuestion(wording.id, text);
      }
    },
    onSuccess: onSaved,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const kept = wordings.filter((w) => w.text.trim()).length;

  return (
    <form className="item-editor" onSubmit={submit} aria-label="Edit question">
      <label>
        Title (shown in lists)
        <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset>
        <legend>Question wordings</legend>
        {wordings.map((wording, index) => (
          <div key={wording.id ?? `new-${index}`} className="wording">
            <label className="sr-only" htmlFor={`wording-${item.id}-${index}`}>
              Wording {index + 1}
            </label>
            <textarea
              id={`wording-${item.id}-${index}`}
              rows={2}
              value={wording.text}
              onChange={(e) => setWordings(wordings.map((w, i) => (i === index ? { ...w, text: e.target.value } : w)))}
            />
            <button
              type="button"
              className="link danger"
              disabled={wordings.length <= 1}
              onClick={() => {
                if (wording.id) setRemoved([...removed, wording.id]);
                setWordings(wordings.filter((_, i) => i !== index));
              }}
            >
              Remove
            </button>
          </div>
        ))}
        <button type="button" className="link" onClick={() => setWordings([...wordings, { id: null, text: "" }])}>
          + Add another wording
        </button>
      </fieldset>
      <label>
        Expected answer
        <textarea rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </label>
      <label>
        Key points (one per line, up to 10)
        <textarea rows={3} value={points} onChange={(e) => setPoints(e.target.value)} />
      </label>
      <ErrorBanner error={save.error} />
      <div className="actions">
        <button type="submit" className="primary" disabled={save.isPending || !title.trim() || kept === 0}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

type MoveTarget = {
  target_concept_id?: string;
  target_topic_id?: string;
  delete_emptied_concepts: boolean;
};

function MoveForm({
  chapters,
  count,
  busy,
  onMove,
  onCancel,
}: {
  chapters: Chapter[];
  count: number;
  busy: boolean;
  onMove: (target: MoveTarget) => void;
  onCancel: () => void;
}) {
  const [target, setTarget] = useState("");
  const [removeEmpty, setRemoveEmpty] = useState(true);
  const selectId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const [kind, id] = target.split(":");
    if (!id) return;
    if (kind === "concept") onMove({ target_concept_id: id, delete_emptied_concepts: removeEmpty });
    else onMove({ target_topic_id: id, delete_emptied_concepts: removeEmpty });
  };
  return (
    <form className="card move-form" onSubmit={submit} aria-label="Move questions">
      <label htmlFor={selectId}>
        Move {count} {count === 1 ? "question" : "questions"} to
      </label>
      <select id={selectId} value={target} onChange={(e) => setTarget(e.target.value)} required>
        <option value="" disabled>
          Choose a topic or a concept…
        </option>
        {chapters.map((chapter) => (
          <optgroup key={chapter.id} label={chapter.title}>
            {chapter.topics.map((topic) => [
              <option key={topic.id} value={`topic:${topic.id}`}>
                {`Topic: ${topic.title} (each question keeps its own concept)`}
              </option>,
              ...topic.concepts.map((concept) => (
                <option key={concept.id} value={`concept:${concept.id}`}>
                  {`   ↳ into concept: ${concept.title}`}
                </option>
              )),
            ])}
          </optgroup>
        ))}
      </select>
      <label className="toggle">
        <input type="checkbox" checked={removeEmpty} onChange={(e) => setRemoveEmpty(e.target.checked)} />
        Remove concepts left without questions
      </label>
      <p className="hint">Questions keep their review progress. In a concept that isn't active, they aren't reviewed until it is.</p>
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={!target || busy}>
          Move
        </button>
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Selects every shown question inside a chapter, topic or concept; partly selected shows a dash. */
function GroupCheckbox({
  label,
  ids,
  selected,
  onToggle,
}: {
  label: string;
  ids: string[];
  selected: Set<string>;
  onToggle: (ids: string[], on: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const count = ids.filter((id) => selected.has(id)).length;
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = count > 0 && count < ids.length;
  }, [count, ids.length]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className="group-checkbox"
      checked={ids.length > 0 && count === ids.length}
      onChange={(e) => onToggle(ids, e.target.checked)}
      aria-label={`Select every question in ${label}`}
    />
  );
}
