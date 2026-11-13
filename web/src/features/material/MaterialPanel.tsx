import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type FormEvent } from "react";
import type { Schemas } from "../../api/client";
import { documents } from "../../api/endpoints";
import { userMessage } from "../../api/client";
import { CollapseToggle, useCollapsed } from "../../components/Collapsible";
import { HelpTip } from "../../components/HelpTip";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { Icon } from "../../components/Icon";
import { PRIORITIES, PriorityBadge } from "../../components/PriorityBadge";
import { useI18n } from "../../i18n";
import { bankPrompt } from "./bankPrompt";
import { outlineKey } from "../curriculum/CourseLayout";

const ACCEPT = ".pdf,.docx,.pptx,.txt,.md,.markdown,image/*,.apkg,.xlsx,.csv,.tsv";
// Question banks are read by their text labels: text formats only.
const ACCEPT_QUESTIONS = ".pdf,.docx,.txt,.md,.markdown,.apkg,.xlsx,.csv,.tsv";

type Purpose = Schemas["DocumentPurpose"];

/** A Course's (or one Chapter's) study material: upload, processing status, delete. */
export function MaterialPanel({ courseId, chapterId }: { courseId: string; chapterId?: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const key = ["documents", courseId, chapterId ?? "all"];
  const list = useQuery({
    queryKey: key,
    queryFn: () => documents.list(courseId, chapterId),
    // Processing happens in the background on the server: follow it until it settles.
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "PROCESSING") ? 2000 : false),
  });
  const materialInput = useRef<HTMLInputElement>(null);
  const questionsInput = useRef<HTMLInputElement>(null);
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["documents", courseId] });
    // An imported question bank adds Chapters, Topics and Concepts.
    void queryClient.invalidateQueries({ queryKey: outlineKey(courseId) });
  };
  const upload = useMutation({
    mutationFn: ({ file, purpose }: { file: File; purpose: Purpose }) =>
      documents.upload(courseId, file, chapterId, purpose),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: documents.remove, onSuccess: invalidate });
  const pending = upload.isPending ? upload.variables.purpose : null;
  const [pasting, setPasting] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const collapse = useCollapsed("learnable.material.collapsed");
  const panelId = `material-${chapterId ?? courseId}`;
  const expanded = !collapse.isCollapsed(panelId);

  const download = async (documentId: string, filename: string) => {
    setDownloadError(null);
    try {
      const blob = await documents.download(documentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(userMessage(e, t));
    }
  };

  const fileInput = (ref: typeof materialInput, accept: string, purpose: Purpose, testId: string) => (
    <input
      ref={ref}
      type="file"
      accept={accept}
      hidden
      data-testid={testId}
      onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) upload.mutate({ file, purpose });
        event.target.value = "";
      }}
    />
  );

  return (
    <section className="card" aria-labelledby="material-heading">
      <header className="card-header">
        <div className="section-heading">
          <CollapseToggle
            expanded={expanded}
            onToggle={() => collapse.toggle(panelId)}
            label={t("mat.collapseLabel")}
            controls={`${panelId}-body`}
          />
          <h2 id="material-heading">{chapterId ? t("mat.chapterTitle") : t("course.allMaterial")}</h2>
          <HelpTip text="help.material" topic={t("menu.material")} guide="material" />
          {!expanded && list.data && (
            <span className="hint">
              {t(list.data.length === 1 ? "mat.files.one" : "mat.files.other", { n: list.data.length })}
            </span>
          )}
        </div>
        <div className="actions">
          <button type="button" onClick={() => materialInput.current?.click()} disabled={upload.isPending}>
            {pending === "MATERIAL" ? t("mat.uploading") : t("mat.upload")}
          </button>
          <button type="button" onClick={() => questionsInput.current?.click()} disabled={upload.isPending}>
            {pending === "QUESTION_BANK" ? t("mat.uploading") : t("mat.uploadQa")}
          </button>
          <button type="button" aria-expanded={pasting} onClick={() => setPasting((v) => !v)} disabled={upload.isPending}>
            {t("mat.paste")}
          </button>
        </div>
        {fileInput(materialInput, ACCEPT, "MATERIAL", "material-input")}
        {fileInput(questionsInput, ACCEPT_QUESTIONS, "QUESTION_BANK", "questions-input")}
      </header>
      <div id={`${panelId}-body`} hidden={!expanded}>
      <details className="hint format-help">
        <summary>{t("mat.howTo")}</summary>
        <p>{t("mat.howToBody")}</p>
        <pre>{"# Topic\nDomanda: What is …?\nRisposta: It is …\nPriorità: 2"}</pre>
        <p>{t("mat.howToBody2")}</p>
        <p>
          <strong>{t("mat.importOther")}</strong> {t("mat.importOtherBody")}
        </p>
        <PriorityHelp />
        <ChatbotPrompt />
      </details>
      {pasting && (
        <PasteTextForm
          busy={upload.isPending}
          onSubmit={(file, purpose) =>
            upload.mutate(
              { file, purpose },
              {
                onSuccess: () => setPasting(false),
              },
            )
          }
          onCancel={() => setPasting(false)}
        />
      )}
      <ErrorBanner error={upload.error ?? remove.error} />
      {downloadError && (
        <p role="alert" className="banner error">
          {downloadError}
        </p>
      )}
      <QueryState query={list} label={t("mat.loading")}>
        {(items) =>
          items.length === 0 ? (
            <p className="hint">{t("mat.none")}</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t("mat.file")}</th>
                  <th scope="col">{t("mat.status")}</th>
                  <th scope="col">{t("mat.passages")}</th>
                  <th scope="col">{t("mat.added")}</th>
                  <th scope="col">
                    <span className="sr-only">{t("mat.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      {doc.filename}
                      {doc.purpose === "QUESTION_BANK" && <span className="pill"> {t("mat.qa")}</span>}
                    </td>
                    <td>
                      <span className={`pill status-${doc.status.toLowerCase()}`}>
                        {doc.status === "PROCESSING" ? t("mat.processing") : doc.status === "READY" ? t("mat.ready") : t("mat.failed")}
                      </span>
                      {doc.error_message && <span className="hint"> {doc.error_message}</span>}
                      {doc.import_notice && <span className="hint"> {doc.import_notice}</span>}
                    </td>
                    <td>{doc.chunk_count}</td>
                    <td>{dateTime(doc.created_at)}</td>
                    <td>
                      <button type="button" className="link" onClick={() => void download(doc.id, doc.filename)}>
                        {t("mat.download")}
                      </button>
                      <button
                        type="button"
                        className="link danger"
                        onClick={() => {
                          if (window.confirm(t("mat.confirmDelete", { name: doc.filename }))) {
                            remove.mutate(doc.id);
                          }
                        }}
                      >
                        {t("common.delete")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </QueryState>
      </div>
    </section>
  );
}

export function CourseMaterialPage({ courseId }: { courseId: string }) {
  return (
    <div className="page">
      <MaterialPanel courseId={courseId} />
    </div>
  );
}

/** Paste text instead of uploading a file: it's sent as a Markdown file, so "# headings" still
 * become sections, and "Domanda:" / "Risposta:" labels work for questions and answers. */
function PasteTextForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  onSubmit: (file: File, purpose: Purpose) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [purpose, setPurpose] = useState<Purpose>("MATERIAL");
  const textId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    const name = (title.trim() || t("mat.pastedName", { when: new Date().toISOString().slice(0, 16).replace("T", " ") }))
      .replace(/[\\/:*?"<>|]+/g, " ")
      .slice(0, 150);
    onSubmit(new File([text], `${name}.md`, { type: "text/markdown" }), purpose);
  };
  return (
    <form className="paste-form" onSubmit={submit} aria-label={t("mat.pasteAria")}>
      <label>
        {t("common.title")}
        <input value={title} maxLength={150} placeholder={t("mat.pastePlaceholder")} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset className="purpose-choice">
        <legend>{t("mat.thisTextIs")}</legend>
        <label className="toggle">
          <input type="radio" name="paste-purpose" checked={purpose === "MATERIAL"} onChange={() => setPurpose("MATERIAL")} />
          {t("mat.asMaterial")}
        </label>
        <label className="toggle">
          <input type="radio" name="paste-purpose" checked={purpose === "QUESTION_BANK"} onChange={() => setPurpose("QUESTION_BANK")} />
          {t("mat.asQa")}
        </label>
      </fieldset>
      <label htmlFor={textId}>{t("mat.text")}</label>
      <textarea
        id={textId}
        rows={12}
        required
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={purpose === "QUESTION_BANK" ? t("mat.textPlaceholderQa") : t("mat.textPlaceholder")}
      />
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={busy || !text.trim()}>
          {busy ? t("mat.adding") : t("mat.addText")}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

/** The five priorities and how to write one in the file. */
function PriorityHelp() {
  const { t } = useI18n();
  return (
    <div className="format-prompt">
      <p>{t("mat.priorityHelp")}</p>
      <ul className="priority-legend">
        {PRIORITIES.map((p) => (
          <li key={p}>
            <code>{p}</code> <PriorityBadge priority={p} /> {t(`priority.${p}.hint` as "priority.1.hint")}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A ready prompt for the chatbot the user prefers: paste it with the notes, get back a file in
 * the import format with a priority on every question. One tap copies it.
 */
function ChatbotPrompt() {
  const { t, language } = useI18n();
  const [copied, setCopied] = useState(false);
  const [shown, setShown] = useState(false);
  const prompt = bankPrompt(language);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
    } catch {
      // No clipboard access (an old browser, or not allowed): show the text to copy by hand.
      setShown(true);
    }
  };
  return (
    <div className="format-prompt">
      <h3 className="with-icon">
        <Icon name="chat" size={18} /> {t("mat.promptTitle")}
      </h3>
      <p>{t("mat.promptIntro")}</p>
      <ol className="steps">
        <li>{t("mat.promptStep1")}</li>
        <li>{t("mat.promptStep2")}</li>
        <li>{t("mat.promptStep3")}</li>
        <li>{t("mat.promptStep4")}</li>
      </ol>
      <div className="actions">
        <button type="button" className="primary" onClick={() => void copy()}>
          {copied ? t("mat.promptCopied") : t("mat.promptCopy")}
        </button>
        <button type="button" className="link" aria-expanded={shown} onClick={() => setShown((v) => !v)}>
          {shown ? t("mat.promptHide") : t("mat.promptShow")}
        </button>
      </div>
      <span className="sr-only" role="status">
        {copied ? t("mat.promptCopied") : ""}
      </span>
      {shown && <pre tabIndex={0}>{prompt}</pre>}
      <p className="hint">{t("mat.promptNote")}</p>
    </div>
  );
}
