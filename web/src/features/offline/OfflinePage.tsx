import { useMemo, useState, useSyncExternalStore } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { useOffline } from "../../pwa";
import { answeredIds, enqueue, packs, queue, subscribe, sync } from "./store";

type Outcome = Schemas["ReviewOutcome"];
const OUTCOMES: Outcome[] = ["AGAIN", "HARD", "GOOD", "EASY"];

function useStore<T>(read: () => T): T {
  // localStorage reads are cheap; a JSON string keeps the snapshot stable between changes.
  const snapshot = useSyncExternalStore(subscribe, () => JSON.stringify(read()));
  return useMemo(() => JSON.parse(snapshot) as T, [snapshot]);
}

/**
 * Reviewing a downloaded course without a network: read the question, answer if you like, see
 * the reference answer and grade yourself. Answers wait on the device and are sent when it is
 * back online (store.sync), each applied at the moment it was given.
 */
export function OfflinePage() {
  const { t } = useI18n();
  const { outcomeLabel } = useLabels();
  const { courseId = "" } = useParams();
  const offline = useOffline();
  const all = useStore(packs);
  const waiting = useStore(queue).filter((a) => a.course_id === courseId).length;
  const pack = all[courseId];
  const [early, setEarly] = useState(false);
  const [text, setText] = useState("");
  const [shown, setShown] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<number | null>(null);
  // "Due now" as of opening the page (questions don't fall due while it's open).
  const [now] = useState(() => Date.now());

  if (!pack) {
    return (
      <div className="page offline-page">
        <p className="state">{t("offline.notDownloaded")}</p>
        <Link to="/review">← {t("nav.review")}</Link>
      </div>
    );
  }
  const done = answeredIds(courseId);
  const left = pack.cards.filter((card) => !done.has(card.learning_item_id));
  const due = left.filter((card) => new Date(card.due_at).getTime() <= now);
  const list = early ? left : due;
  const card = list[0];

  const grade = (outcome: Outcome) => {
    if (!card) return;
    enqueue({
      course_id: courseId,
      learning_item_id: card.learning_item_id,
      question_formulation_id: card.question_formulation_id,
      text: text.trim(),
      outcome,
    });
    setText("");
    setShown(false);
  };
  const send = async () => {
    setSending(true);
    setSent(await sync());
    setSending(false);
  };

  return (
    <div className="page offline-page">
      <p className="breadcrumbs">
        <Link to="/review">← {t("nav.review")}</Link>
      </p>
      <div className="page-header">
        <h1>{pack.title}</h1>
        <p className="hint">
          {t("offline.packInfo", { n: pack.cards.length, date: new Date(pack.created_at).toLocaleDateString() })}
        </p>
      </div>
      <div className="offline-status card">
        <span>{offline ? t("offline.youAreOffline") : t("offline.youAreOnline")}</span>
        {waiting > 0 && <strong>{t("offline.waiting", { n: waiting })}</strong>}
        {waiting > 0 && !offline && (
          <button type="button" className="primary" disabled={sending} onClick={() => void send()}>
            {sending ? t("common.pleaseWait") : t("offline.sendNow")}
          </button>
        )}
        {sent !== null && <span className="hint" role="status">{t("offline.sent", { n: sent })}</span>}
      </div>

      {!card ? (
        <section className="card offline-done">
          <p className="state caught-up">{t("offline.allDone")}</p>
          {!early && left.length > 0 && (
            <button type="button" onClick={() => setEarly(true)}>
              {t("offline.reviewEarly", { n: left.length })}
            </button>
          )}
        </section>
      ) : (
        <section className="card offline-card" aria-live="polite">
          <span className="eyebrow">{t("offline.leftNow", { n: list.length })}</span>
          <h2 className="question">{card.question}</h2>
          {!shown ? (
            <>
              <label className="sr-only" htmlFor="offline-answer">
                {t("study.yourAnswer")}
              </label>
              <textarea
                id="offline-answer"
                rows={4}
                value={text}
                placeholder={card.drawing ? t("offline.drawingHint") : t("offline.answerPlaceholder")}
                onChange={(e) => setText(e.target.value)}
              />
              <button type="button" className="primary" onClick={() => setShown(true)}>
                {t("offline.show")}
              </button>
            </>
          ) : (
            <>
              {text.trim() && (
                <div className="your-answer">
                  <h3>{t("study.yourAnswer")}</h3>
                  <p>{text}</p>
                </div>
              )}
              <div className="reference">
                <h3>{t("study.reference")}</h3>
                <p className="reading">{card.expected_knowledge}</p>
                {card.essential_points.length > 0 && (
                  <ul>
                    {card.essential_points.map((point, i) => (
                      <li key={i}>{point}</li>
                    ))}
                  </ul>
                )}
              </div>
              <p className="hint">{t("offline.gradeYourself")}</p>
              <div className="grade" role="group" aria-label={t("offline.gradeYourself")}>
                {OUTCOMES.map((outcome) => (
                  <button key={outcome} type="button" className={`grade-${outcome.toLowerCase()}`} onClick={() => grade(outcome)}>
                    {outcomeLabel[outcome]}
                  </button>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
