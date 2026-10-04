import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/messages/en";

/**
 * A "?" button next to a heading: opens a short explanation of that part of the screen, with a
 * link to the matching guide section. Closes on Escape or a click elsewhere.
 */
export function HelpTip({ text, topic, guide }: { text: MessageKey; topic: string; guide?: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <span className="help-tip" ref={box}>
      <button
        type="button"
        className="help-button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={t("help.button", { topic })}
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {open && (
        <span className="help-bubble" id={id} role="note">
          {t(text)}
          {guide && (
            <Link to={`/guide#guide-${guide}`} onClick={() => setOpen(false)}>
              {t("help.more")}
            </Link>
          )}
        </span>
      )}
    </span>
  );
}
