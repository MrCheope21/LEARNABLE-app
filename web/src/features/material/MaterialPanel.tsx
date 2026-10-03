import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type FormEvent } from "react";
import type { Schemas } from "../../api/client";
import { documents } from "../../api/endpoints";
import { userMessage } from "../../api/client";
import { CollapseToggle, useCollapsed } from "../../components/Collapsible";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { outlineKey } from "../curriculum/CourseLayout";

const ACCEPT = ".pdf,.docx,.pptx,.txt,.md,.markdown,image/*";
// Question banks are read by their text labels: text formats only.
const ACCEPT_QUESTIONS = ".pdf,.docx,.txt,.md,.markdown";

type Purpose = Schemas["DocumentPurpose"];

/** A Course's (or one Chapter's) study material: upload, processing status, delete. */
export function MaterialPanel({ courseId, chapterId }: { courseId: string; chapterId?: string }) {
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
      setDownloadError(userMessage(e));
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
            label="study material"
            controls={`${panelId}-body`}
          />
          <h2 id="material-heading">{chapterId ? "Chapter material" : "All study material"}</h2>
          {!expanded && list.data && (
            <span className="hint">
              {list.data.length} {list.data.length === 1 ? "file" : "files"}
            </span>
          )}
        </div>
        <div className="actions">
          <button type="button" onClick={() => materialInput.current?.click()} disabled={upload.isPending}>
            {pending === "MATERIAL" ? "Uploading…" : "Upload material"}
          </button>
          <button type="button" onClick={() => questionsInput.current?.click()} disabled={upload.isPending}>
            {pending === "QUESTION_BANK" ? "Uploading…" : "Upload questions & answers"}
          </button>
          <button type="button" aria-expanded={pasting} onClick={() => setPasting((v) => !v)} disabled={upload.isPending}>
            Paste text
          </button>
        </div>
        {fileInput(materialInput, ACCEPT, "MATERIAL", "material-input")}
        {fileInput(questionsInput, ACCEPT_QUESTIONS, "QUESTION_BANK", "questions-input")}
      </header>
      <div id={`${panelId}-body`} hidden={!expanded}>
      <details className="hint format-help">
        <summary>How to prepare questions &amp; answers</summary>
        <p>
          Upload a PDF, Word, text or Markdown file where each question starts with <code>Domanda:</code> and its
          expected answer with <code>Risposta:</code> (or <code>Question:</code> / <code>Answer:</code>), at the
          beginning of a line. Headings group the questions into topics.
        </p>
        <pre>{"# Topic\nDomanda: What is …?\nRisposta: It is …"}</pre>
        <p>
          Each question becomes a concept marked not studied, with your answer as the expected answer. Activate it
          to start reviewing. No AI is used for the import.
        </p>
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
      <QueryState query={list} label="Loading material…">
        {(items) =>
          items.length === 0 ? (
            <p className="hint">No material yet. Upload PDF, Word, PowerPoint, text or Markdown files.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">File</th>
                  <th scope="col">Status</th>
                  <th scope="col">Passages</th>
                  <th scope="col">Added</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      {doc.filename}
                      {doc.purpose === "QUESTION_BANK" && <span className="pill"> Q&amp;A</span>}
                    </td>
                    <td>
                      <span className={`pill status-${doc.status.toLowerCase()}`}>
                        {doc.status === "PROCESSING" ? "Processing…" : doc.status === "READY" ? "Ready" : "Failed"}
                      </span>
                      {doc.error_message && <span className="hint"> {doc.error_message}</span>}
                      {doc.import_notice && <span className="hint"> {doc.import_notice}</span>}
                    </td>
                    <td>{doc.chunk_count}</td>
                    <td>{dateTime(doc.created_at)}</td>
                    <td>
                      <button type="button" className="link" onClick={() => void download(doc.id, doc.filename)}>
                        Download
                      </button>
                      <button
                        type="button"
                        className="link danger"
                        onClick={() => {
                          if (window.confirm(`Delete ${doc.filename}? Concepts built from it will be flagged for review.`)) {
                            remove.mutate(doc.id);
                          }
                        }}
                      >
                        Delete
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
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [purpose, setPurpose] = useState<Purpose>("MATERIAL");
  const textId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    const name = (title.trim() || `Pasted text ${new Date().toISOString().slice(0, 16).replace("T", " ")}`)
      .replace(/[\\/:*?"<>|]+/g, " ")
      .slice(0, 150);
    onSubmit(new File([text], `${name}.md`, { type: "text/markdown" }), purpose);
  };
  return (
    <form className="paste-form" onSubmit={submit} aria-label="Paste text">
      <label>
        Title
        <input value={title} maxLength={150} placeholder="e.g. Lecture 3 notes" onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset className="purpose-choice">
        <legend>This text is</legend>
        <label className="toggle">
          <input type="radio" name="paste-purpose" checked={purpose === "MATERIAL"} onChange={() => setPurpose("MATERIAL")} />
          Study material
        </label>
        <label className="toggle">
          <input type="radio" name="paste-purpose" checked={purpose === "QUESTION_BANK"} onChange={() => setPurpose("QUESTION_BANK")} />
          Questions &amp; answers (Domanda: / Risposta:)
        </label>
      </fieldset>
      <label htmlFor={textId}>Text</label>
      <textarea
        id={textId}
        rows={12}
        required
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={purpose === "QUESTION_BANK" ? "# Topic\nDomanda: …?\nRisposta: …" : "# Heading\nYour notes…"}
      />
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={busy || !text.trim()}>
          {busy ? "Adding…" : "Add text"}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
