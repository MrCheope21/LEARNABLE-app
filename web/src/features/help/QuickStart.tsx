import { useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

const STORAGE_KEY = "learnable.quick-start-hidden";

// Each step shows the real screen it refers to (web/public/guide, captured from the app).
export const STEPS = [
  { key: "material", image: "/guide/material.jpg", guide: "material" },
  { key: "plan", image: "/guide/proposal.jpg", guide: "curriculum" },
  { key: "study", image: "/guide/question.jpg", guide: "study" },
  { key: "review", image: "/guide/dashboard.jpg", guide: "review" },
] as const;

function hidden(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** "How LEARNABLE works" in four illustrated steps, on the dashboard until the user hides it. */
export function QuickStart({ forceOpen = false }: { forceOpen?: boolean }) {
  const { t } = useI18n();
  const [isHidden, setHidden] = useState(() => !forceOpen && hidden());
  const toggle = (value: boolean) => {
    setHidden(value);
    try {
      if (value) localStorage.setItem(STORAGE_KEY, "1");
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Not remembered; it shows again next time.
    }
  };
  if (isHidden) {
    return (
      <button type="button" className="link quick-start-reopen" onClick={() => toggle(false)}>
        {t("start.reopen")}
      </button>
    );
  }
  return (
    <section className="card quick-start" aria-labelledby="quick-start-title">
      <header className="quick-start-header">
        <div>
          <h2 id="quick-start-title">{t("start.title")}</h2>
          <p className="hint">{t("start.intro")}</p>
        </div>
        <button type="button" className="link" onClick={() => toggle(true)}>
          {t("start.hide")}
        </button>
      </header>
      <ol className="quick-steps">
        {STEPS.map((step, index) => (
          <li key={step.key} className="quick-step" style={{ animationDelay: `${index * 120}ms` }}>
            <img src={step.image} alt="" loading="lazy" />
            <span className="step-number" aria-hidden="true">
              {index + 1}
            </span>
            <strong>{t(`start.${step.key}.title` as MessageKey)}</strong>
            <span className="hint">{t(`start.${step.key}.body` as MessageKey)}</span>
            <Link to={`/guide#guide-${step.guide}`}>{t("help.more")}</Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
