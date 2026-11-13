import { Link } from "react-router-dom";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

const SECTIONS = ["data", "who", "ai", "payments", "keep", "rights"] as const;

/** The privacy notice: what is stored, who sees it, and how to delete everything. */
export function PrivacyPage({ signedIn = true }: { signedIn?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="page guide-page privacy-page">
      <div className="page-header">
        <h1>{t("privacy.title")}</h1>
        <p className="lead">{t("privacy.intro")}</p>
      </div>
      {SECTIONS.map((id) => (
        <section key={id} className="card guide-section" aria-labelledby={`privacy-${id}`}>
          <h2 id={`privacy-${id}`}>{t(`privacy.${id}.title` as MessageKey)}</h2>
          <p>{t(`privacy.${id}.body` as MessageKey)}</p>
        </section>
      ))}
      <p>{signedIn ? <Link to="/settings#settings-security-section">{t("privacy.toSettings")}</Link> : <Link to="/">← {t("privacy.back")}</Link>}</p>
    </div>
  );
}
