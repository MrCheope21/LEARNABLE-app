import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { marketplace } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { categoryIcon } from "./labels";

/**
 * A course's marketplace page, as its author wrote it: what it covers, who it's for, what you'll
 * learn, and its size (chapters and question counts). The questions themselves show only once
 * the course is in your courses.
 */
export function ListingPage() {
  const { t } = useI18n();
  const { categoryLabel, levelLabel, languageName, priceLabel, count } = useLabels();
  const { listingId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const listing = useQuery({ queryKey: ["listing", listingId], queryFn: () => marketplace.get(listingId) });
  const acquire = useMutation({
    mutationFn: () => marketplace.acquire(listingId),
    onSuccess: ({ course_id }) => {
      for (const key of [["dashboard"], ["courses"], ["marketplace"], ["listing", listingId]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
      navigate(`/courses/${course_id}`);
    },
  });

  return (
    <div className="page listing-page">
      <p className="breadcrumbs">
        <Link to="/marketplace">← {t("nav.marketplace")}</Link>
      </p>
      <QueryState query={listing} label={t("mkt.loadingCourse")}>
        {(data) => (
          <>
            <header className="card listing-hero">
              <span className="listing-category">
                {categoryIcon[data.category]} {categoryLabel[data.category]}
              </span>
              <h1>{data.title}</h1>
              {data.subtitle && <p className="listing-subtitle">{data.subtitle}</p>}
              <p className="hint">
                {t("mkt.by", { author: data.author })} · {levelLabel[data.level]} · {languageName(data.language)}
                {data.published_at && ` · ${t("mkt.updated", { date: dateTime(data.updated_at) })}`}
              </p>
              <dl className="listing-stats">
                <div>
                  <dt>{t("concept.questions")}</dt>
                  <dd>{data.item_count}</dd>
                </div>
                <div>
                  <dt>{t("course.chapters")}</dt>
                  <dd>{data.chapter_count}</dd>
                </div>
                <div>
                  <dt>{t("mkt.statStudents")}</dt>
                  <dd>{data.acquisition_count}</dd>
                </div>
              </dl>
              <div className="actions">
                {data.is_mine ? (
                  <span className="pill">{t("mkt.yourCourse")}{data.status !== "PUBLISHED" && ` · ${data.status === "DRAFT" ? t("mkt.draftTag") : t("mkt.notPublishedTag")}`}</span>
                ) : data.course_id ? (
                  <Link className="button primary" to={`/courses/${data.course_id}`}>
                    {t("mkt.open")}
                  </Link>
                ) : (
                  <button type="button" className="primary" disabled={acquire.isPending} onClick={() => acquire.mutate()}>
                    {data.has_access ? t("mkt.addBack") : t("mkt.add", { price: priceLabel(data) })}
                  </button>
                )}
              </div>
              <ErrorBanner error={acquire.error} />
            </header>

            <section className="card">
              <h2>{t("mkt.about")}</h2>
              <p className="reading listing-description">{data.description}</p>
            </section>

            {data.outcomes.length > 0 && (
              <section className="card">
                <h2>{t("mkt.learn")}</h2>
                <ul className="outcomes">
                  {data.outcomes.map((o, i) => (
                    <li key={i}>{o}</li>
                  ))}
                </ul>
              </section>
            )}

            {data.audience && (
              <section className="card">
                <h2>{t("mkt.audience")}</h2>
                <p className="reading">{data.audience}</p>
              </section>
            )}

            <section className="card">
              <h2>{t("course.chapters")}</h2>
              <ol className="listing-chapters">
                {data.chapters.map((chapter, i) => (
                  <li key={i}>
                    <span>{chapter.title}</span>
                    <span className="hint">{count("unit.question", chapter.questions)}</span>
                  </li>
                ))}
              </ol>
              <p className="hint">{t("mkt.hiddenNote")}</p>
            </section>
          </>
        )}
      </QueryState>
    </div>
  );
}
