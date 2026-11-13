import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { userMessage } from "../api/client";
import { useI18n } from "../i18n";

/** Loading, error with retry, or the content: never an endless spinner, never a raw error. */
export function QueryState<T>({
  query,
  children,
  label,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  label?: string;
}) {
  const { t } = useI18n();
  if (query.isPending) {
    return (
      <div className="state skeleton-state" role="status" aria-busy="true">
        <span className="sr-only">{label ?? t("common.loading")}</span>
        <div className="skeleton" aria-hidden="true">
          <span className="skeleton-line wide" />
          <span className="skeleton-line" />
          <span className="skeleton-line short" />
        </div>
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="state error-state" role="alert">
        <p>{userMessage(query.error, t)}</p>
        <button type="button" onClick={() => void query.refetch()}>
          {t("common.tryAgain")}
        </button>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}

export function ErrorBanner({ error, onDismiss }: { error: unknown; onDismiss?: () => void }) {
  const { t } = useI18n();
  if (!error) return null;
  return (
    <div className="banner error" role="alert">
      <span>{userMessage(error, t)}</span>
      {onDismiss && (
        <button type="button" className="link" onClick={onDismiss} aria-label={t("common.dismiss")}>
          ×
        </button>
      )}
    </div>
  );
}
