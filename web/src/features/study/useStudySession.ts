import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, userMessage, type Schemas } from "../../api/client";
import { useI18n } from "../../i18n";
import { study } from "../../api/endpoints";
import { drafts } from "./drafts";

export type Card = Schemas["Card"];
export type AnswerView = Schemas["AnswerResult"];

export type Phase =
  | { kind: "starting" }
  | { kind: "introduction"; card: Card }
  | { kind: "answering"; card: Card }
  | { kind: "submitting"; card: Card }
  | { kind: "result"; card: Card; result: AnswerView }
  | { kind: "finished" }
  | { kind: "empty" }
  | { kind: "failed"; message: string };

/**
 * Drives one study session (LEARN, SCHEDULED_REVIEW or PRACTICE). The backend picks questions,
 * evaluates, resolves outcomes and moves the schedule; this only follows it. It never computes a
 * memory level, an outcome or a due date.
 */
export function useStudySession(courseId: string, request: Schemas["SessionCreate"], resumeId: string | null = null) {
  const { t } = useI18n();
  const [phase, setPhase] = useState<Phase>({ kind: "starting" });
  const [session, setSession] = useState<Schemas["SessionRead"] | null>(null);
  const [draft, setDraftState] = useState("");
  // The answer was (at least partly) dictated; the backend records how it was given.
  const [dictated, setDictated] = useState(false);
  // A drawing question's answer (a data URL), or null while nothing is drawn.
  const [drawing, setDrawing] = useState<string | null>(null);
  const draftRef = useRef("");
  const [error, setError] = useState<unknown>(null);
  const [working, setWorking] = useState(false);
  // Final outcome per answer: an override replaces its answer's entry.
  const [outcomes, setOutcomes] = useState<Record<string, Schemas["ReviewOutcome"]>>({});
  // Every answer's latest result in this sitting (for the end-of-session summary).
  const [results, setResults] = useState<Record<string, AnswerView>>({});
  const sessionRef = useRef<Schemas["SessionRead"] | null>(null);
  const started = useRef(false);

  const record = useCallback((result: AnswerView) => {
    const outcome = result.final_outcome;
    if (outcome) setOutcomes((current) => ({ ...current, [result.answer_id]: outcome }));
    setResults((current) => ({ ...current, [result.answer_id]: result }));
    // The session's XP so far comes back with every result.
    sessionRef.current = result.session;
    setSession(result.session);
  }, []);

  const loadNext = useCallback(async () => {
    const current = sessionRef.current;
    if (!current) return;
    try {
      const next = await study.next(current.id);
      sessionRef.current = next.session;
      setSession(next.session);
      const card = next.card;
      if (next.done || !card) {
        setPhase({ kind: "finished" });
        return;
      }
      if (card.pending_answer_id) {
        // An earlier answer to this card still has no outcome (e.g. the evaluation failed):
        // show it as its result so it can be graded or re-evaluated.
        const pending = await study.getAnswer(card.pending_answer_id);
        setPhase({ kind: "result", card, result: pending });
        return;
      }
      const saved = drafts.load(card.question.id);
      setDraftState(saved);
      draftRef.current = saved;
      setDictated(false);
      setDrawing(null);
      setPhase(card.introduction ? { kind: "introduction", card } : { kind: "answering", card });
    } catch (e) {
      setPhase({ kind: "failed", message: userMessage(e, t) });
    }
  }, [t]);

  const start = useCallback(async () => {
    setPhase({ kind: "starting" });
    try {
      // A stored session (e.g. an unfinished consolidation batch) is resumed, never recreated.
      const created = resumeId ? await study.get(resumeId) : await study.start(courseId, request);
      sessionRef.current = created;
      setSession(created);
    } catch (e) {
      // The only conflict when starting: nothing qualifies right now (docs/API.md empty_pool).
      if (e instanceof ApiError && e.status === 409) setPhase({ kind: "empty" });
      else setPhase({ kind: "failed", message: userMessage(e, t) });
      return;
    }
    await loadNext();
  }, [courseId, request, resumeId, loadNext, t]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  const setDraft = useCallback(
    (text: string) => {
      setDraftState(text);
      draftRef.current = text;
      if (!text.trim()) setDictated(false);
      if (phase.kind === "answering") drafts.save(phase.card.question.id, text);
    },
    [phase],
  );

  /** Adds a dictated phrase after what is already written. */
  const appendDictation = useCallback(
    (phrase: string) => {
      if (!phrase) return;
      const current = draftRef.current.trimEnd();
      setDraft(current ? `${current} ${phrase}` : phrase);
      setDictated(true);
    },
    [setDraft],
  );

  const beginRecall = useCallback(() => {
    if (phase.kind === "introduction") setPhase({ kind: "answering", card: phase.card });
  }, [phase]);

  const drawn = phase.kind === "answering" && phase.card.answer_format === "DRAWING";
  const canSubmit = phase.kind === "answering" && (drawn ? drawing !== null : draft.trim().length > 0);

  const submit = useCallback(async () => {
    const current = sessionRef.current;
    if (phase.kind !== "answering" || !current || !canSubmit) return;
    const card = phase.card;
    setPhase({ kind: "submitting", card });
    setError(null);
    try {
      const result = await study.answer(
        current.id,
        card.question.id,
        draft.trim(),
        dictated ? "VOICE" : "TEXT",
        card.answer_format === "DRAWING" ? (drawing ?? undefined) : undefined,
      );
      // The backend has the answer: the local copy can go.
      drafts.clear(card.question.id);
      setDraftState("");
      draftRef.current = "";
      setDictated(false);
      setDrawing(null);
      record(result);
      setPhase({ kind: "result", card, result });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // The session moved on (e.g. the answer arrived but the response was lost): resync.
        // The draft stays saved.
        await loadNext();
        return;
      }
      setPhase({ kind: "answering", card });
      setError(e);
    }
  }, [phase, draft, dictated, drawing, canSubmit, record, loadNext]);

  const withResult = useCallback(
    async (action: (result: AnswerView) => Promise<AnswerView>) => {
      if (phase.kind !== "result") return;
      setWorking(true);
      setError(null);
      try {
        const updated = await action(phase.result);
        record(updated);
        setPhase({ kind: "result", card: phase.card, result: updated });
      } catch (e) {
        setError(e);
      } finally {
        setWorking(false);
      }
    },
    [phase, record],
  );

  /** The user's own grade. The AI evaluation stays as it was; this is stored beside it. */
  const override = useCallback(
    (outcome: Schemas["ReviewOutcome"]) => withResult((r) => study.override(r.answer_id, outcome)),
    [withResult],
  );

  /** A mostly green answer, repeated after reviewing the reference: it counts as correct. */
  const repeat = useCallback((text: string) => withResult((r) => study.repeat(r.answer_id, text)), [withResult]);

  /** Asks the evaluator again with the student's objection; no grade changes. */
  const dispute = useCallback(
    (argument: string) => withResult((r) => study.dispute(r.answer_id, argument)),
    [withResult],
  );

  /** Reveals the hint for the current question. The server records it first (half XP). */
  const revealHint = useCallback(async () => {
    const current = sessionRef.current;
    if (!current || phase.kind !== "answering") return;
    const card = phase.card;
    setWorking(true);
    setError(null);
    try {
      const hint = await study.hint(current.id);
      setPhase({ kind: "answering", card: { ...card, hint } });
    } catch (e) {
      setError(e);
    } finally {
      setWorking(false);
    }
  }, [phase]);

  const retryEvaluation = useCallback(
    () => withResult((r) => study.retryEvaluation(r.answer_id)),
    [withResult],
  );

  const skip = useCallback(async () => {
    const current = sessionRef.current;
    if (!current) return;
    setWorking(true);
    try {
      await study.skip(current.id);
      await loadNext();
    } catch (e) {
      setError(e);
    } finally {
      setWorking(false);
    }
  }, [loadNext]);

  const end = useCallback(async () => {
    const current = sessionRef.current;
    if (!current || current.ended_at) return;
    try {
      await study.end(current.id);
    } catch {
      // Ending is housekeeping; leaving the screen shouldn't fail on it.
    }
  }, []);

  return {
    phase,
    session,
    draft,
    setDraft,
    appendDictation,
    setDrawing,
    canSubmit,
    error,
    clearError: () => setError(null),
    working,
    outcomes,
    results,
    start,
    loadNext,
    beginRecall,
    submit,
    override,
    repeat,
    dispute,
    revealHint,
    retryEvaluation,
    skip,
    end,
  };
}
