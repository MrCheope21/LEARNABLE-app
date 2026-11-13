import { useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

const SECTIONS = ["structure", "material", "curriculum", "study", "answer", "disagree", "review", "progress", "organise", "marketplace", "community"] as const;
type Section = (typeof SECTIONS)[number];
// Real screens of the app (web/public/guide), one per step that has one.
const IMAGES: Partial<Record<Section, string>> = {
  structure: "/guide/course.jpg",
  material: "/guide/material.jpg",
  curriculum: "/guide/proposal.jpg",
  study: "/guide/concept.jpg",
  answer: "/guide/result.jpg",
  disagree: "/guide/dispute.jpg",
  review: "/guide/dashboard.jpg",
  progress: "/guide/weak-spots.jpg",
  organise: "/guide/questions.jpg",
  marketplace: "/guide/marketplace.jpg",
};
const TERMS = ["concept", "item", "active", "grades", "mastery", "xp"] as const;

const bare = (title: string) => title.replace(/^\d+\.\s*/, "");

/**
 * "How Recallable works", one step at a time: the steps as a row of numbered buttons, the step
 * itself with its screen, and Back / Next (also the arrow keys). Links from the app point at a
 * step ("/guide#guide-review").
 */
export function GuidePage() {
  const { t } = useI18n();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const fromHash = SECTIONS.indexOf(hash.replace("#guide-", "") as Section);
  // The step lives in the address ("#guide-review"), so links and Back / Forward work.
  const index = Math.max(0, fromHash);
  const go = (next: number) => {
    const clamped = Math.min(SECTIONS.length - 1, Math.max(0, next));
    navigate(`#guide-${SECTIONS[clamped]}`, { replace: true });
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
      const forward = document.documentElement.dir === "rtl" ? "ArrowLeft" : "ArrowRight";
      const back = forward === "ArrowRight" ? "ArrowLeft" : "ArrowRight";
      if (event.key === forward) go(index + 1);
      if (event.key === back) go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const id = SECTIONS[index] as Section;
  const image = IMAGES[id];
  const last = index === SECTIONS.length - 1;
  return (
    <div className="page guide-page">
      <div className="page-header">
        <h1>{t("guide.title")}</h1>
        <p className="lead">{t("guide.intro")}</p>
      </div>
      <nav className="guide-steps" aria-label={t("guide.contents")}>
        {SECTIONS.map((section, i) => (
          <button
            key={section}
            type="button"
            className={i === index ? "guide-step current" : i < index ? "guide-step seen" : "guide-step"}
            aria-current={i === index ? "step" : undefined}
            title={bare(t(`guide.${section}.title` as MessageKey))}
            aria-label={`${i + 1}. ${bare(t(`guide.${section}.title` as MessageKey))}`}
            onClick={() => go(i)}
          >
            {i + 1}
          </button>
        ))}
      </nav>
      <div className="guide-track" aria-hidden="true">
        <span style={{ width: `${((index + 1) / SECTIONS.length) * 100}%` }} />
      </div>
      <section key={id} id={`guide-${id}`} className="card guide-section guide-card" aria-labelledby={`guide-${id}-title`} aria-live="polite">
        <span className="eyebrow">{t("guide.stepOf", { n: index + 1, total: SECTIONS.length })}</span>
        <h2 id={`guide-${id}-title`}>{bare(t(`guide.${id}.title` as MessageKey))}</h2>
        <p>{t(`guide.${id}.body` as MessageKey)}</p>
        {image && (
          <a href={image} target="_blank" rel="noopener" className="guide-shot">
            <img src={image} alt="" width={1200} height={760} />
          </a>
        )}
        <div className="guide-nav">
          <button type="button" disabled={index === 0} onClick={() => go(index - 1)}>
            {t("guide.prev")}
          </button>
          {last ? (
            <Link className="button primary" to="/">
              {t("guide.finish")}
            </Link>
          ) : (
            <button type="button" className="primary" onClick={() => go(index + 1)}>
              {t("guide.next")}: {bare(t(`guide.${SECTIONS[index + 1]}.title` as MessageKey))}
            </button>
          )}
        </div>
      </section>
      <details className="card guide-section guide-more">
        <summary>{t("guide.glossary.title")}</summary>
        <dl className="glossary">
          {TERMS.map((term) => (
            <div key={term}>
              <dt>{t(`guide.term.${term}` as MessageKey)}</dt>
              <dd>{t(`guide.term.${term}.def` as MessageKey)}</dd>
            </div>
          ))}
        </dl>
      </details>
      <details className="card guide-section guide-more">
        <summary>{t("guide.privacy.title")}</summary>
        <p>{t("guide.privacy.body")}</p>
        <p>
          <Link to="/privacy">{t("privacy.title")}</Link>
        </p>
      </details>
    </div>
  );
}
