import { useMutation } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { reports, type ReportKind } from "../api/endpoints";
import { useI18n } from "../i18n";
import { ErrorBanner } from "./QueryState";

/** "Report": tells the administrator about a person, a message or a review, with an optional reason. */
export function ReportButton({ kind, targetId }: { kind: ReportKind; targetId: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const id = useId();
  const send = useMutation({ mutationFn: () => reports.send(kind, targetId, reason.trim()) });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send.mutate();
  };
  if (send.isSuccess) {
    return (
      <span className="hint report-sent" role="status">
        {t("report.sent")}
      </span>
    );
  }
  if (!open) {
    return (
      <button type="button" className="link report-link" onClick={() => setOpen(true)}>
        {t("report.button")}
      </button>
    );
  }
  return (
    <form className="report-form" onSubmit={submit}>
      <label htmlFor={id}>{t("report.why")}</label>
      <textarea id={id} rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
      <p className="hint">{t("report.hint")}</p>
      <div className="actions">
        <button type="submit" className="primary" disabled={send.isPending}>
          {t("report.send")}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          {t("common.cancel")}
        </button>
      </div>
      <ErrorBanner error={send.error} />
    </form>
  );
}
