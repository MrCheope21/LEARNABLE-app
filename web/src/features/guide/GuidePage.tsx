import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

const SECTIONS = ["structure", "material", "curriculum", "study", "answer", "disagree", "review", "progress", "organise"] as const;
const TERMS = ["concept", "item", "active", "grades", "mastery", "xp"] as const;

/** "How LEARNABLE works": the whole study loop on one page, in the interface language. */
export function GuidePage() {
  const { t } = useI18n();
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
