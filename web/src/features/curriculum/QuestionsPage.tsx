import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { courses, learningItems, reorder } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { CollapsibleSection, useCollapsed } from "../../components/Collapsible";
import { HelpTip } from "../../components/HelpTip";
import { Icon } from "../../components/Icon";
import { SortableList } from "../../components/SortableList";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";
import { Breadcrumbs } from "./Consolidate";
import { useReadOnlyCourse } from "../../components/CourseAccess";
import { PriorityBadge, PrioritySelect, PRIORITIES } from "../../components/PriorityBadge";
import { Tooltip } from "../../components/Tooltip";
import { studyLink } from "../study/StudyPage";
import { QuestionImageEditor } from "./QuestionImageEditor";
import { ReferenceDrawingEditor } from "./ReferenceDrawingEditor";
import { removalFor, type Removal } from "./selection";
import { courseProgressKey, outlineKey } from "./CourseLayout";

type Item = Schemas["LearningItemRead"];

const PAGE = 100;
type Chapter = Schemas["ChapterOutline"];

export const courseItemsKey = (courseId: string) => ["course-items", courseId] as const;

/**
 * Every question of a Course in one place: select one or many, then delete, pause, resume or
 * move them (into a concept, or into a topic where each keeps its own concept); edit one
 * inline. The server applies bulk actions all or nothing.
 */
export function QuestionsPage() {
  const { t } = useI18n();
  const { priorityLabel } = useLabels();
  const unit = (base: string, n: number) => t(`${base}.${n === 1 ? "one" : "other"}` as MessageKey, { n });
  const { courseId = "" } = useParams();
  const queryClient = useQueryClient();
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const items = useQuery({ queryKey: courseItemsKey(courseId), queryFn: () => learningItems.listForCourse(courseId) });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState<number | null>(null);
  // Where to look: a chapter (and a topic in it), or the whole course.
  const [chapterFilter, setChapterFilter] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  // Long courses render a page of questions at a time.
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const searchId = useId();
  const readOnly = useReadOnlyCourse();
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
      const verb = t(`q.verb.${body.action}` as MessageKey);
      const extra = [
        result.created_concepts ? unit("q.newConcepts", result.created_concepts) : null,
        result.deleted_concepts ? unit("q.removedConcepts", result.deleted_concepts) : null,
      ].filter(Boolean);
      setNotice(t("q.noticeBulk", { verb, questions: unit("unit.question", result.affected), extra: extra.length ? ` · ${extra.join(" · ")}` : "" }));
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
        groups
          ? t("q.noticeDeletedGroups", { questions: unit("unit.question", questions), groups: unit("unit.group", groups) })
          : t("q.noticeDeleted", { questions: unit("unit.question", questions) }),
      );
      setSelected(new Set());
      setMoving(false);
      refresh();
    },
  });

  const visible = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    const all = (items.data ?? []).filter(
      (item) =>
        (priorityFilter === null || item.priority === priorityFilter) &&
        (!chapterFilter || item.chapter_id === chapterFilter) &&
        (!topicFilter || item.topic_id === topicFilter),
    );
    if (!needle) return all;
    return all.filter(
      (item) =>
        item.title.toLocaleLowerCase().includes(needle) ||
        item.expected_knowledge.toLocaleLowerCase().includes(needle) ||
        item.questions.some((q) => q.text.toLocaleLowerCase().includes(needle)),
    );
  }, [items.data, filter, priorityFilter, chapterFilter, topicFilter]);

  // One question at a time: delete it (own course) or leave it out of reviews (any course).
  const tidy = useMutation({
    mutationFn: () => learningItems.detectChoices(courseId),
    onSuccess: ({ converted }) => {
      setNotice(t("q.tidyDone", { n: converted }));
      refresh();
    },
  });
  const removeOne = (item: Item) => {
    const text = item.questions[0]?.text ?? item.title;
    if (!window.confirm(t("q.deleteOneConfirm", { text: text.length > 120 ? `${text.slice(0, 120)}…` : text }))) return;
    remove.mutate({ removal: removalFor(outline.data ?? [], items.data ?? [], new Set([item.id])), questions: 1 });
  };
  const pauseOne = (item: Item) =>
    bulk.mutate({ item_ids: [item.id], action: item.paused ? "resume" : "pause", delete_emptied_concepts: false });

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
      [removal.chapterIds.length, "unit.chapter"],
      [removal.topicIds.length, "unit.topic"],
      [removal.conceptIds.length, "unit.concept"],
    ]
      .filter(([n]) => Number(n) > 0)
      .map(([n, base]) => unit(String(base), Number(n)));
    const also = groups.length ? t("q.confirmAlso", { groups: groups.join(", ") }) : "";
    if (window.confirm(t("q.confirmDelete", { questions: unit("unit.question", count), also }))) {
      remove.mutate({ removal, questions: count });
    }
  };

  return (
    <div className="page questions-page">
      <Breadcrumbs courseId={courseId} current={t("q.title")} />
      <div className="page-header">
        <div className="title-row">
          <h1>{t("q.title")}</h1>
          <HelpTip text="help.questions" topic={t("q.title")} guide="organise" />
        </div>
        <p className="hint">
          {readOnly ? t("q.introManaged") : t("q.introOwn")}
        </p>
      </div>

      {!readOnly && (
        <div className="tidy-bar">
          <button type="button" disabled={tidy.isPending} onClick={() => tidy.mutate()}>
            {tidy.isPending ? t("common.pleaseWait") : t("q.tidy")}
          </button>
          <span className="hint">{t("q.tidyHint")}</span>
        </div>
      )}
      <div className="toolbar">
        <label className="sr-only" htmlFor={searchId}>
          {t("q.search")}
        </label>
        <input id={searchId} type="search" placeholder={t("q.searchPlaceholder")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        <label className="sr-only" htmlFor={`${searchId}-priority`}>
          {t("priority.label")}
        </label>
        <select
          id={`${searchId}-priority`}
          className="priority-filter"
          value={priorityFilter ?? ""}
          onChange={(e) => setPriorityFilter(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t("q.allPriorities")}</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {t("q.priorityOnly", { label: priorityLabel[p] ?? "", n: (items.data ?? []).filter((i) => i.priority === p).length })}
            </option>
          ))}
        </select>
        {(outline.data?.length ?? 0) > 1 && (
          <select
            aria-label={t("q.chapterFilter")}
            value={chapterFilter}
            onChange={(e) => {
              setChapterFilter(e.target.value);
              setTopicFilter("");
              setLimit(PAGE);
            }}
          >
            <option value="">{t("q.allChapters")}</option>
            {outline.data?.map((chapter) => (
              <option key={chapter.id} value={chapter.id}>
                {chapter.title}
              </option>
            ))}
          </select>
        )}
        {chapterFilter && (outline.data?.find((c) => c.id === chapterFilter)?.topics.length ?? 0) > 1 && (
          <select
            aria-label={t("q.topicFilter")}
            value={topicFilter}
            onChange={(e) => {
              setTopicFilter(e.target.value);
              setLimit(PAGE);
            }}
          >
            <option value="">{t("q.allTopics")}</option>
            {outline.data
              ?.find((c) => c.id === chapterFilter)
              ?.topics.map((topic) => (
                <option key={topic.id} value={topic.id}>
                  {topic.title}
                </option>
              ))}
          </select>
        )}
        <button type="button" disabled={visible.length === 0} onClick={() => toggle(visible.map((i) => i.id), !allVisibleSelected)}>
          {allVisibleSelected ? t("q.deselectAll") : t(filter.trim() ? "q.selectAllShown" : "q.selectAll", { n: visible.length })}
        </button>
        <button type="button" className="link" disabled={Boolean(filter.trim())} onClick={() => sections.setAll(sectionIds, true)}>
          {t("q.collapseAll")}
        </button>
        <button type="button" className="link" disabled={Boolean(filter.trim())} onClick={() => sections.setAll(sectionIds, false)}>
          {t("q.expandAll")}
        </button>
      </div>

      {selected.size > 0 && (
        <div className="bulk-bar" role="toolbar" aria-label={t("q.selectedAria")}>
          <strong>{t("q.selectedCount", { n: selected.size })}</strong>
          {!readOnly && (
            <button type="button" className="primary" aria-expanded={moving} onClick={() => setMoving((v) => !v)}>
              {t("q.moveTo")}
            </button>
          )}
          <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate({ item_ids: ids, action: "pause", delete_emptied_concepts: false })}>
            {t("menu.pause")}
          </button>
          <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate({ item_ids: ids, action: "resume", delete_emptied_concepts: false })}>
            {t("menu.resume")}
          </button>
          <label className="sr-only" htmlFor={`${searchId}-set-priority`}>
            {t("q.setPriority")}
          </label>
          <select
            id={`${searchId}-set-priority`}
            value=""
            disabled={bulk.isPending}
            onChange={(e) => e.target.value && bulk.mutate({ item_ids: ids, action: "set_priority", priority: Number(e.target.value), delete_emptied_concepts: false })}
          >
            <option value="">{t("q.setPriorityPlaceholder")}</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {priorityLabel[p]}
              </option>
            ))}
          </select>
          <Tooltip text={t("q.reviewSelectedHelp")}>
            <Link className="button" to={studyLink(courseId, "PRACTICE", { itemIds: ids.slice(0, 100) })}>
              {t("concept.reviewOwn")}
            </Link>
          </Tooltip>
          {!readOnly && (
            <button type="button" className="danger" disabled={bulk.isPending || remove.isPending} onClick={confirmDelete}>
              {t("common.delete")}
            </button>
          )}
          <button type="button" className="link" onClick={() => setSelected(new Set())}>
            {t("q.clearSelection")}
          </button>
        </div>
      )}
      {moving && outline.data && selected.size > 0 && (
        <MoveForm chapters={outline.data} count={selected.size} busy={bulk.isPending} onMove={(target) => bulk.mutate({ item_ids: ids, action: "move", ...target })} onCancel={() => setMoving(false)} />
      )}
      {notice && (
        <p className="banner info" role="status">
          {notice}
          <button type="button" className="link" onClick={() => setNotice(null)} aria-label={t("common.dismiss")}>
            ×
          </button>
        </p>
      )}
      <ErrorBanner error={bulk.error ?? remove.error ?? tidy.error} />

      <QueryState query={outline}>
        {(chapters) => (
          <QueryState query={items}>
            {() => {
              // In course order, the first `limit` questions; the rest behind "Show more".
              const ordered = chapters.flatMap((c) => c.topics.flatMap((tp) => tp.concepts.map((k) => k.id)));
              const rank = new Map(ordered.map((id, index) => [id, index]));
              const inOrder = [...visible].sort((a, b) => (rank.get(a.concept_id) ?? 0) - (rank.get(b.concept_id) ?? 0) || a.order - b.order);
              const page = inOrder.slice(0, limit);
              const hidden = inOrder.length - page.length;
              const byConcept = new Map<string, Item[]>();
              for (const item of page) byConcept.set(item.concept_id, [...(byConcept.get(item.concept_id) ?? []), item]);
              const anything = chapters.some((c) => c.topics.some((t) => t.concepts.some((k) => byConcept.has(k.id))));
              if (!anything) {
                return <p className="state">{filter ? t("q.emptySearch") : t("q.empty")}</p>;
              }
              const idsIn = (concepts: { id: string }[]) => concepts.flatMap((k) => (byConcept.get(k.id) ?? []).map((i) => i.id));
              const section = (id: string, label: string) => ({ id, label, expanded: open(id), onToggle: () => sections.toggle(id) });
              const row = (item: Item) => (
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
                  onDelete={() => removeOne(item)}
                  onPause={() => pauseOne(item)}
                  busy={remove.isPending || bulk.isPending}
                />
              );
              const questionList = (conceptId: string, conceptItems: Item[]) => (
                <SortableList
                  className="question-list"
                  items={conceptItems}
                  itemLabel={(item) => item.questions[0]?.text ?? item.title}
                  disabledReason={filter.trim() ? t("q.clearToReorder") : undefined}
                  onReorder={async (ids) => {
                    await reorder.learningItems(conceptId, ids);
                    refresh();
                  }}
                  renderItem={row}
                />
              );
              const groups = chapters.map((chapter) => {
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
                            const [only] = conceptItems;
                            if (conceptItems.length === 1 && only) {
                              // A concept holding one question (as imports make them): the question alone.
                              return (
                                <div key={concept.id} className="question-single">
                                  {row(only)}
                                </div>
                              );
                            }
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
                                    {unit("unit.question", conceptItems.length)}
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
              return (
                <>
                  {groups}
                  {hidden > 0 && (
                    <div className="show-more">
                      <span className="hint">{t("q.shownOf", { n: page.length, total: inOrder.length })}</span>
                      <button type="button" onClick={() => setLimit(limit + PAGE * 2)}>
                        {t("q.showMore", { n: Math.min(hidden, PAGE * 2) })}
                      </button>
                    </div>
                  )}
                </>
              );
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
  onDelete,
  onPause,
  busy,
}: {
  item: Item;
  selected: boolean;
  onSelect: (on: boolean) => void;
  editing: boolean;
  onEdit: () => void;
  onSaved: () => void;
  onDelete: () => void;
  onPause: () => void;
  busy: boolean;
}) {
  const { t } = useI18n();
  const { memoryStateLabel } = useLabels();
  const first = item.questions[0]?.text ?? item.title;
  const others = item.questions.length - 1;
  const readOnly = useReadOnlyCourse();
  return (
    <div className={selected ? "question-row selected" : "question-row"}>
      <input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} aria-label={t("q.select", { text: first })} />
      <div className="question-text">
        <span>
          {first} <PriorityBadge priority={item.priority} />
          {item.answer_format === "CHOICE" && <span className="pill">{t("choice.badge")}</span>}
        </span>
        <span className="hint">
          {others > 0 && `${t(others === 1 ? "q.otherWordings.one" : "q.otherWordings.other", { n: others })} · `}
          {memoryStateLabel[item.review_state.state]}
          {item.paused && ` · ${t("card.paused")}`}
          {!item.in_training && ` · ${t("concept.notTraining")}`}
        </span>
      </div>
      <span className="row-actions">
        {readOnly ? (
          <PrioritySelect item={item} onSaved={onSaved} />
        ) : (
          <button type="button" className="link" aria-expanded={editing} onClick={onEdit}>
            {editing ? t("common.close") : t("common.edit")}
          </button>
        )}
        <button type="button" className="link" disabled={busy} onClick={onPause} title={item.paused ? t("q.resumeOneHint") : t("q.pauseOneHint")}>
          {item.paused ? t("q.resumeOne") : t("q.pauseOne")}
        </button>
        {!readOnly && (
          <button type="button" className="icon-button danger" disabled={busy} onClick={onDelete} aria-label={t("q.deleteOne", { text: first })} title={t("common.delete")}>
            <Icon name="trash" size={18} />
          </button>
        )}
      </span>
      {editing && !readOnly && (
        <>
          <ItemEditor item={item} onSaved={onSaved} />
          <QuestionImageEditor item={item} onChanged={onSaved} />
          <ReferenceDrawingEditor item={item} onChanged={onSaved} />
        </>
      )}
    </div>
  );
}

/** Edits the item's title, wordings, expected answer and key points. Memory state is kept. */
function ItemEditor({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const { t } = useI18n();
  const [title, setTitle] = useState(item.title);
  const [wordings, setWordings] = useState(item.questions.map((q) => ({ id: q.id as string | null, text: q.text })));
  const [removed, setRemoved] = useState<string[]>([]);
  const [answer, setAnswer] = useState(item.expected_knowledge);
  const [points, setPoints] = useState(item.essential_points.join("\n"));
  const [priority, setPriority] = useState(item.priority);
  // Multiple choice: on when the item has options; off sends [] to turn it back into a written answer.
  const [choosing, setChoosing] = useState(item.answer_format === "CHOICE");
  const [options, setOptions] = useState<{ text: string; correct: boolean }[]>(
    item.choices?.length ? item.choices.map((c) => ({ text: c.text, correct: c.correct })) : [
      { text: "", correct: true },
      { text: "", correct: false },
      { text: "", correct: false },
    ],
  );
  const filled = options.filter((o) => o.text.trim());
  const optionsValid = !choosing || (filled.length >= 2 && filled.some((o) => o.correct));
  const save = useMutation({
    mutationFn: async () => {
      const keyPoints = points
        .split("\n")
        .map((p) => p.trim())
        .filter(Boolean)
        .slice(0, 10);
      const choices = choosing
        ? filled.map((o) => ({ text: o.text.trim(), correct: o.correct }))
        : item.answer_format === "CHOICE"
          ? []
          : undefined;
      await learningItems.update(item.id, {
        title: title.trim(),
        expected_knowledge: answer,
        essential_points: keyPoints,
        priority,
        ...(choices !== undefined ? { choices } : {}),
      });
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
    <form className="item-editor" onSubmit={submit} aria-label={t("q.editAria")}>
      <label>
        {t("q.titleLabel")}
        <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset>
        <legend>{t("q.wordings")}</legend>
        {wordings.map((wording, index) => (
          <div key={wording.id ?? `new-${index}`} className="wording">
            <label className="sr-only" htmlFor={`wording-${item.id}-${index}`}>
              {t("q.wording", { n: index + 1 })}
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
              {t("common.remove")}
            </button>
          </div>
        ))}
        <button type="button" className="link" onClick={() => setWordings([...wordings, { id: null, text: "" }])}>
          {t("q.addWording")}
        </button>
      </fieldset>
      {item.answer_format !== "DRAWING" && (
        <fieldset className="choice-editor">
          <legend>{t("choice.editorTitle")}</legend>
          <label className="toggle">
            <input type="checkbox" checked={choosing} onChange={(e) => setChoosing(e.target.checked)} />
            {t("choice.enable")}
          </label>
          {choosing && (
            <>
              <p className="hint">{t("choice.editorHint")}</p>
              <ol className="choice-edit-list">
                {options.map((option, index) => (
                  <li key={index}>
                    <input
                      aria-label={t("choice.optionN", { n: index + 1 })}
                      value={option.text}
                      maxLength={500}
                      onChange={(e) => setOptions(options.map((o, i) => (i === index ? { ...o, text: e.target.value } : o)))}
                    />
                    <label className="choice-correct">
                      <input
                        type="checkbox"
                        checked={option.correct}
                        onChange={(e) => setOptions(options.map((o, i) => (i === index ? { ...o, correct: e.target.checked } : o)))}
                      />
                      {t("choice.correct")}
                    </label>
                    <button type="button" className="link danger" disabled={options.length <= 2} onClick={() => setOptions(options.filter((_, i) => i !== index))}>
                      {t("common.remove")}
                    </button>
                  </li>
                ))}
              </ol>
              {options.length < 8 && (
                <button type="button" className="link" onClick={() => setOptions([...options, { text: "", correct: false }])}>
                  {t("choice.addOption")}
                </button>
              )}
              {!optionsValid && <p className="error">{t("choice.invalid")}</p>}
            </>
          )}
        </fieldset>
      )}
      <label>
        {choosing ? t("choice.explanation") : t("q.expected")}
        <textarea rows={choosing ? 3 : 5} value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </label>
      <label>
        {t("priority.label")}
        <select value={priority} onChange={(e) => setPriority(Number(e.target.value))}>
          <option value={1}>{t("q.prio1")}</option>
          <option value={2}>{t("q.prio2")}</option>
          <option value={3}>{t("q.prio3")}</option>
        </select>
      </label>
      <label>
        {t("q.keyPoints")}
        <textarea rows={3} value={points} onChange={(e) => setPoints(e.target.value)} />
      </label>
      <ErrorBanner error={save.error} />
      <div className="actions">
        <button type="submit" className="primary" disabled={save.isPending || !title.trim() || kept === 0 || !optionsValid}>
          {save.isPending ? t("common.saving") : t("common.save")}
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
  const { t } = useI18n();
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
    <form className="card move-form" onSubmit={submit} aria-label={t("q.moveAria")}>
      <label htmlFor={selectId}>
        {t("q.moveHeading", { questions: t(count === 1 ? "unit.question.one" : "unit.question.other", { n: count }) })}
      </label>
      <select id={selectId} value={target} onChange={(e) => setTarget(e.target.value)} required>
        <option value="" disabled>
          {t("q.choose")}
        </option>
        {chapters.map((chapter) => (
          <optgroup key={chapter.id} label={chapter.title}>
            {chapter.topics.map((topic) => [
              <option key={topic.id} value={`topic:${topic.id}`}>
                {t("q.topicOption", { title: topic.title })}
              </option>,
              ...topic.concepts.map((concept) => (
                <option key={concept.id} value={`concept:${concept.id}`}>
                  {t("q.conceptOption", { title: concept.title })}
                </option>
              )),
            ])}
          </optgroup>
        ))}
      </select>
      <label className="toggle">
        <input type="checkbox" checked={removeEmpty} onChange={(e) => setRemoveEmpty(e.target.checked)} />
        {t("q.removeEmpty")}
      </label>
      <p className="hint">{t("q.moveHint")}</p>
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={!target || busy}>
          {t("q.move")}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          {t("common.cancel")}
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
  const { t } = useI18n();
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
      aria-label={t("q.groupSelect", { label })}
    />
  );
}
