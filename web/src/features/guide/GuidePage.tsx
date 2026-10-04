import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

const SECTIONS = ["structure", "material", "curriculum", "study", "answer", "disagree", "review", "progress", "organise", "marketplace"] as const;
// Real screens of the app (web/public/guide), one per step.
const IMAGES: Record<(typeof SECTIONS)[number], string> = {
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

/** "How LEARNABLE works": the whole study loop on one page, in the interface language. */
export function GuidePage() {
  const { t } = useI18n();
  const { hash } = useLocation();
  // "Learn more" links point at a section: bring it into view.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);
  return (
    <div className="page guide-page">
      <header className="page-header">
        <h1>{t("guide.title")}</h1>
        <p className="lead">{t("guide.intro")}</p>
      </header>
      <nav className="card guide-contents" aria-label={t("guide.contents")}>
        <h2>{t("guide.contents")}</h2>
        <ol>
          {SECTIONS.map((id) => (
            <li key={id}>
              <a href={`#guide-${id}`}>{t(`guide.${id}.title` as MessageKey).replace(/^\d+\.\s*/, "")}</a>
            </li>
          ))}
        </ol>
      </nav>
      {SECTIONS.map((id) => (
        <section key={id} id={`guide-${id}`} className="card guide-section" aria-labelledby={`guide-${id}-title`}>
          <h2 id={`guide-${id}-title`}>{t(`guide.${id}.title` as MessageKey)}</h2>
          <p>{t(`guide.${id}.body` as MessageKey)}</p>
          <a href={IMAGES[id]} target="_blank" rel="noopener" className="guide-shot">
            <img src={IMAGES[id]} alt={t(`guide.${id}.title` as MessageKey)} loading="lazy" width={1200} height={760} />
          </a>
        </section>
      ))}
      <section className="card guide-section" aria-labelledby="guide-glossary">
        <h2 id="guide-glossary">{t("guide.glossary.title")}</h2>
        <dl className="glossary">
          {TERMS.map((term) => (
            <div key={term}>
              <dt>{t(`guide.term.${term}` as MessageKey)}</dt>
              <dd>{t(`guide.term.${term}.def` as MessageKey)}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="card guide-section" aria-labelledby="guide-privacy">
        <h2 id="guide-privacy">{t("guide.privacy.title")}</h2>
        <p>{t("guide.privacy.body")}</p>
      </section>
    </div>
  );
}
