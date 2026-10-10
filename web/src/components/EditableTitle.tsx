import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { userMessage } from "../api/client";
import { useI18n } from "../i18n";
import { useReadOnlyCourse } from "./CourseAccess";

/**
 * A page title with "Rename": edits the title (and description) of a course, chapter, topic or
 * concept in place. `onSave` performs the PATCH; the caller refreshes what shows the title.
 */
export function EditableTitle({
  title,
  description,
  label,
  headingId,
  onSave,
}: {
  title: string;
  description?: string | null;
  label: string;
  headingId?: string;
  onSave: (values: { title: string; description: string }) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [draftDescription, setDraftDescription] = useState(description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const titleId = useId();
  const descriptionId = useId();
  const { t } = useI18n();
  const readOnly = useReadOnlyCourse();

  const start = () => {
    setDraftTitle(title);
    setDraftDescription(description ?? "");
    setError(null);
    setEditing(true);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draftTitle.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSave({ title: draftTitle.trim(), description: draftDescription.trim() });
      setEditing(false);
    } catch (e) {
      setError(userMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") setEditing(false);
  };

  if (!editing) {
    return (
      <div className="editable-title">
        <div className="editable-title-row">
          <h1 id={headingId}>{title}</h1>
          {!readOnly && (
            <button type="button" className="link" onClick={start} aria-label={t("editTitle.rename", { label })}>
              {t("common.rename")}
            </button>
          )}
        </div>
        {description && <p className="hint">{description}</p>}
      </div>
    );
  }
  return (
    <form className="editable-title editing" onSubmit={submit} onKeyDown={onKeyDown} aria-label={t("editTitle.rename", { label })}>
      <label htmlFor={titleId}>{t("common.title")}</label>
      <input id={titleId} value={draftTitle} maxLength={200} required autoFocus onChange={(e) => setDraftTitle(e.target.value)} />
      <label htmlFor={descriptionId}>{t("common.description")}</label>
      <textarea id={descriptionId} rows={2} maxLength={2000} value={draftDescription} onChange={(e) => setDraftDescription(e.target.value)} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={busy || !draftTitle.trim()}>
          {busy ? t("common.saving") : t("common.save")}
        </button>
        <button type="button" className="link" onClick={() => setEditing(false)}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}
