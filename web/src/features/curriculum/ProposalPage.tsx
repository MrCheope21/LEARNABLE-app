import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { curriculum } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { sourceSummary } from "../../components/labels";
import { courseProgressKey, outlineKey } from "./CourseLayout";
import {
  applyBody,
  blankConcept,
  draftFrom,
  hasBlankTitles,
  mergeWithNext,
  move,
  moveConcept,
  type DraftChapter,
  type DraftTopic,
} from "./proposalDraft";

/** Polling interval while the AI generates the proposal. Exported for tests. */
export const PROPOSAL_POLL_MS = { value: 1500 };

/**
 * The AI's proposed curriculum, editable before anything reaches the Course
 * (docs/PROJECT_SPEC.md §20). Nothing is activated by accepting it.
 */
export function ProposalPage() {
  const { proposalId = "" } = useParams();
  const proposal = useQuery({
    queryKey: ["proposal", proposalId],
    queryFn: () => curriculum.get(proposalId),
    refetchInterval: (query) => (query.state.data?.status === "GENERATING" ? PROPOSAL_POLL_MS.value : false),
  });

  return (
    <div className="page">
      <header className="page-header">
        <h1>Proposed curriculum</h1>
      </header>
      <QueryState query={proposal}>
        {(data) => {
          if (data.status === "GENERATING") {
            return (
              <p className="state" role="status">
                The AI is reading your material…
              </p>
            );
          }
          if (data.status === "APPLIED") return <p className="state">This proposal has already been applied.</p>;
          if (data.status !== "READY") {
            return <p className="state error-state">{data.error_message ?? "The AI couldn't propose a curriculum."}</p>;
          }
          return <ProposalEditor proposal={data} />;
        }}
      </QueryState>
    </div>
  );
}

function ProposalEditor({ proposal }: { proposal: Schemas["CurriculumProposalRead"] }) {
  const { courseId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // The editable copy is made once, from the proposal as the AI returned it.
  const [initial] = useState(() => draftFrom(proposal));
  const [chapters, setChapters] = useState<DraftChapter[] | null>(initial.chapters);
  const [topics, setTopics] = useState<DraftTopic[]>(initial.topics);
  const [problem, setProblem] = useState<string | null>(null);

  const done = () => {
    void queryClient.invalidateQueries({ queryKey: outlineKey(courseId) });
    void queryClient.invalidateQueries({ queryKey: courseProgressKey(courseId) });
    void queryClient.invalidateQueries({ queryKey: ["proposal", proposal.id] });
    navigate(proposal.chapter_id ? `/courses/${courseId}/chapters/${proposal.chapter_id}` : `/courses/${courseId}`);
  };
  const apply = useMutation({
    mutationFn: () => curriculum.apply(proposal.id, applyBody(chapters, topics)),
    onSuccess: done,
  });
  const reject = useMutation({ mutationFn: () => curriculum.reject(proposal.id), onSuccess: done });

  const empty = chapters ? chapters.length === 0 : topics.length === 0;

  const accept = () => {
    if (hasBlankTitles(chapters, topics)) {
      setProblem("Every chapter, topic and concept needs a title.");
      return;
    }
    setProblem(null);
    apply.mutate();
  };

  return (
    <>
      <section className="card">
        {proposal.passages_used < proposal.passages_total && (
          <p className="banner info">
            The material was long: this covers its first {proposal.passages_used} of {proposal.passages_total} passages.
          </p>
        )}
        {proposal.dropped_concepts > 0 && (
          <p className="banner info">
            {proposal.dropped_concepts} proposed concepts were left out because they couldn't be tied to your material.
          </p>
        )}
        <p className="hint">
          Edit anything below: rename, reorder, move concepts between topics, merge, delete or add. Nothing is activated:
          you choose what to study afterwards.
        </p>
      </section>
      {chapters ? (
        chapters.map((chapter, ci) => (
          <section key={chapter.key} className="card">
            <div className="editor-row">
              <input
                aria-label="Chapter title"
                className="title-input"
                value={chapter.title}
                onChange={(e) => setChapters(chapters.map((c, i) => (i === ci ? { ...c, title: e.target.value } : c)))}
              />
              <button type="button" className="link danger" onClick={() => setChapters(chapters.filter((_, i) => i !== ci))}>
                Delete chapter
              </button>
            </div>
            <TopicsEditor
              topics={chapter.topics}
              onChange={(next) => setChapters(chapters.map((c, i) => (i === ci ? { ...c, topics: next } : c)))}
            />
          </section>
        ))
      ) : (
        <TopicsEditor topics={topics} onChange={setTopics} />
      )}
      <section className="card sticky-actions">
        {problem && (
          <p className="banner error" role="alert">
            {problem}
          </p>
        )}
        <ErrorBanner error={apply.error ?? reject.error} />
        <div className="actions">
          <button type="button" className="primary" disabled={empty || apply.isPending} onClick={accept}>
            Accept curriculum
          </button>
          <button type="button" className="danger" disabled={reject.isPending} onClick={() => reject.mutate()}>
            Reject proposal
          </button>
        </div>
      </section>
    </>
  );
}

function TopicsEditor({ topics, onChange }: { topics: DraftTopic[]; onChange: (topics: DraftTopic[]) => void }) {
  const update = (index: number, topic: DraftTopic) => onChange(topics.map((t, i) => (i === index ? topic : t)));
  return (
    <>
      {topics.map((topic, ti) => (
        <section key={topic.key} className="card topic-editor" aria-label={`Topic ${topic.title || ti + 1}`}>
          <div className="editor-row">
            {topic.existingTopicId ? (
              <h3>
                {topic.title} <span className="pill">existing topic</span>
              </h3>
            ) : (
              <input
                aria-label="Topic title"
                className="title-input"
                value={topic.title}
                onChange={(e) => update(ti, { ...topic, title: e.target.value })}
              />
            )}
            <button type="button" aria-label="Move topic up" disabled={ti === 0} onClick={() => onChange(move(topics, ti, ti - 1))}>
              ↑
            </button>
            <button
              type="button"
              aria-label="Move topic down"
              disabled={ti === topics.length - 1}
              onClick={() => onChange(move(topics, ti, ti + 1))}
            >
              ↓
            </button>
            <button type="button" className="link danger" onClick={() => onChange(topics.filter((_, i) => i !== ti))}>
              Delete topic
            </button>
          </div>
          <ol className="concept-editor">
            {topic.concepts.map((concept, ci) => (
              <li key={concept.key}>
                <div className="editor-row">
                  <input
                    aria-label="Concept title"
                    value={concept.title}
                    onChange={(e) =>
                      update(ti, {
                        ...topic,
                        concepts: topic.concepts.map((c, i) => (i === ci ? { ...c, title: e.target.value } : c)),
                      })
                    }
                  />
                  {concept.existingConceptId && <span className="pill">already exists</span>}
                  <button
                    type="button"
                    aria-label="Move concept up"
                    disabled={ci === 0}
                    onClick={() => update(ti, { ...topic, concepts: move(topic.concepts, ci, ci - 1) })}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label="Move concept down"
                    disabled={ci === topic.concepts.length - 1}
                    onClick={() => update(ti, { ...topic, concepts: move(topic.concepts, ci, ci + 1) })}
                  >
                    ↓
                  </button>
                  {topics.length > 1 && (
                    <select
                      aria-label="Move to topic"
                      value=""
                      onChange={(e) => e.target.value && onChange(moveConcept(topics, concept.key, e.target.value))}
                    >
                      <option value="">Move to…</option>
                      {topics
                        .filter((t) => t.key !== topic.key)
                        .map((t) => (
                          <option key={t.key} value={t.key}>
                            {t.title || "Untitled topic"}
                          </option>
                        ))}
                    </select>
                  )}
                  {ci < topic.concepts.length - 1 && (
                    <button
                      type="button"
                      className="link"
                      onClick={() => update(ti, { ...topic, concepts: mergeWithNext(topic.concepts, ci) })}
                    >
                      Merge with next
                    </button>
                  )}
                  <button
                    type="button"
                    className="link danger"
                    onClick={() => update(ti, { ...topic, concepts: topic.concepts.filter((_, i) => i !== ci) })}
                  >
                    Delete
                  </button>
                </div>
                {concept.sources.length > 0 && (
                  <p className="hint sources-line">{concept.sources.map(sourceSummary).join("; ")}</p>
                )}
              </li>
            ))}
          </ol>
          <button type="button" className="link" onClick={() => update(ti, { ...topic, concepts: [...topic.concepts, blankConcept()] })}>
            + Add concept
          </button>
        </section>
      ))}
    </>
  );
}
