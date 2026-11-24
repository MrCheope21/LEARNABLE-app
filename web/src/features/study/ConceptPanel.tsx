import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { concepts } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";

/**
 * "Study this concept" beside the question: everything the concept teaches (each learning item's
 * expected answer and key points), without leaving the session.
 */
export function ConceptPanel({
  courseId,
  conceptId,
  onClose,
  onNext,
  working = false,
}: {
  courseId: string;
  conceptId: string;
  onClose: () => void;
  /** After an answer: close the panel and go on to the next question. */
  onNext?: () => void;
  working?: boolean;
}) {
  const { t } = useI18n();
  const concept = useQuery({ queryKey: ["concept", conceptId], queryFn: () => concepts.get(conceptId) });
  const items = useQuery({ queryKey: ["items", conceptId], queryFn: () => concepts.learningItems(conceptId) });
  return (
    <aside className="source-panel concept-panel" aria-label={t("conceptPanel.title")}>
      <header>
        <div>
          <span className="eyebrow">{t("conceptPanel.title")}</span>
          <h3>{concept.data?.title ?? "…"}</h3>
        </div>
        <button type="button" className="link" onClick={onClose} aria-label={t("conceptPanel.closeAria")}>
          {t("common.close")}
        </button>
      </header>
      {onNext && (
        <button type="button" className="primary" disabled={working} onClick={onNext}>
          {t("conceptPanel.next")}
        </button>
      )}
      {concept.data?.description && <p>{concept.data.description}</p>}
      <QueryState query={items} label={t("conceptPanel.loading")}>
        {(list) => (
          <ol className="concept-items">
            {list.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>
                <p className="reading">{item.expected_knowledge}</p>
                {item.essential_points.length > 0 && (
                  <ul>
                    {item.essential_points.map((point, index) => (
                      <li key={index}>{point}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        )}
      </QueryState>
      {onNext && (
        <button type="button" className="primary" disabled={working} onClick={onNext}>
          {t("conceptPanel.next")}
        </button>
      )}
      <p className="hint">
        <Link to={`/courses/${courseId}/concepts/${conceptId}`} target="_blank" rel="noopener">
          {t("conceptPanel.openFull")}
        </Link>
      </p>
    </aside>
  );
}
