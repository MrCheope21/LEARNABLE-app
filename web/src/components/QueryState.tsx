import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { userMessage } from "../api/client";

/** Loading, error with retry, or the content: never an endless spinner, never a raw error. */
export function QueryState<T>({
  query,
  children,
  label = "Loading…",
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  label?: string;
}) {
  if (query.isPending) {
    return (
      <div className="state" role="status">
        {label}
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="state error-state" role="alert">
        <p>{userMessage(query.error)}</p>
        <button type="button" onClick={() => void query.refetch()}>
          Try again
        </button>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}

export function ErrorBanner({ error, onDismiss }: { error: unknown; onDismiss?: () => void }) {
  if (!error) return null;
  return (
    <div className="banner error" role="alert">
      <span>{userMessage(error)}</span>
      {onDismiss && (
        <button type="button" className="link" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}
