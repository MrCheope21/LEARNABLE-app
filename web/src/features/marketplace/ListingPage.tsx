import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { marketplace, payments } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { Icon } from "../../components/Icon";
import { Stars } from "../../components/Stars";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { categoryIcon } from "./labels";
import { Reviews } from "./Reviews";

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
  // A paid course: the payment happens on the provider's page, then the browser comes back here
  // with ?order=…; access arrives when the provider confirms, usually within seconds.
  const [code, setCode] = useState("");
  const quote = useMutation({ mutationFn: () => payments.quote(listingId, code.trim()) });
  const applied = quote.data && quote.data.code === code.trim().toUpperCase() ? quote.data : null;
  const buy = useMutation({
    mutationFn: () => payments.checkout(listingId, applied ? applied.code : ""),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const [params, setParams] = useSearchParams();
  const orderId = params.get("order");
  const cancelled = params.get("cancelled") !== null;
  const order = useQuery({
    queryKey: ["order", orderId],
    queryFn: () => payments.order(orderId!),
    enabled: Boolean(orderId),
    refetchInterval: (query) => (query.state.data?.status === "PENDING" ? 2_000 : false),
    retry: false,
  });
  const paidCourse = order.data?.status === "PAID" ? order.data.course_id : null;
  useEffect(() => {
    if (paidCourse) {
      for (const key of [["dashboard"], ["courses"], ["marketplace"], ["listing", listingId]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    }
  }, [paidCourse, listingId, queryClient]);

  return (
    <div className="page listing-page">
      <p className="breadcrumbs">
        <Link to="/marketplace">← {t("nav.marketplace")}</Link>
      </p>
      {orderId && order.data?.status === "PENDING" && (
        <p className="banner info" role="status">
          {t("buy.confirming")}
        </p>
      )}
      {paidCourse && (
        <p className="banner success" role="status">
          {t("buy.done")} <Link to={`/courses/${paidCourse}`}>{t("mkt.open")}</Link>
        </p>
      )}
      {orderId && (order.isError || order.data?.status === "EXPIRED") && (
        <p className="banner warning" role="status">
          {t("buy.failed")}
        </p>
      )}
      {cancelled && (
        <p className="banner info" role="status">
          {t("buy.cancelled")}{" "}
          <button type="button" className="link" onClick={() => setParams({}, { replace: true })}>
            {t("common.dismiss")}
          </button>
        </p>
      )}
      <QueryState query={listing} label={t("mkt.loadingCourse")}>
        {(data) => (
          <>
            <header className="card listing-hero">
              <span className="listing-category">
                <Icon name={categoryIcon[data.category]} size={16} /> {categoryLabel[data.category]}
              </span>
              <h1>{data.title}</h1>
              {data.subtitle && <p className="listing-subtitle">{data.subtitle}</p>}
              <p className="hint">
                {t("mkt.by", { author: data.author })} · {levelLabel[data.level]} · {languageName(data.language)}
                {data.published_at && ` · ${t("mkt.updated", { date: dateTime(data.updated_at) })}`}
              </p>
              {data.rating_average !== null && data.rating_average !== undefined && (
                <p className="listing-rating">
                  <Stars value={data.rating_average} /> <strong>{data.rating_average.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</strong>{" "}
                  <a href="#reviews-title" className="hint">
                    {count("review.count", data.rating_count)}
                  </a>
                </p>
              )}
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
                ) : data.has_access || data.price_cents === 0 ? (
                  <button type="button" className="primary" disabled={acquire.isPending} onClick={() => acquire.mutate()}>
                    {data.has_access ? t("mkt.addBack") : t("mkt.add", { price: priceLabel(data) })}
                  </button>
                ) : (
                  <>
                    <strong className="listing-price">{priceLabel(data)}</strong>
                    <button type="button" className="primary" disabled={!data.can_buy || buy.isPending || order.data?.status === "PENDING"} onClick={() => buy.mutate()}>
                      <Icon name="cart" size={18} /> {buy.isPending ? t("common.pleaseWait") : t("buy.button")}
                    </button>
                  </>
                )}
              </div>
              {!data.is_mine && !data.has_access && data.price_cents > 0 && <p className="hint">{data.can_buy ? t("buy.note") : t("buy.unavailable")}</p>}
              {!data.is_mine && !data.has_access && data.can_buy && (
                <form
                  className="inline-field discount-apply"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (code.trim()) quote.mutate();
                  }}
                >
                  <input value={code} maxLength={40} placeholder={t("discount.have")} aria-label={t("discount.have")} autoCapitalize="characters" onChange={(e) => setCode(e.target.value)} />
                  <button type="submit" disabled={!code.trim() || quote.isPending}>
                    {t("discount.apply")}
                  </button>
                  {applied && (
                    <span className="banner success" role="status">
                      {t("discount.applied", { n: applied.percent_off, price: priceLabel({ price_cents: applied.price_cents, currency: applied.currency }) })}
                    </span>
                  )}
                </form>
              )}
              <ErrorBanner error={acquire.error ?? buy.error ?? quote.error} />
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

            {data.preview.length > 0 && (
              <section className="card" aria-labelledby="preview-title">
                <h2 id="preview-title">{t("mkt.preview")}</h2>
                <p className="hint">{t("mkt.previewHint", { n: data.preview.length, total: data.item_count })}</p>
                <ol className="preview-list">
                  {data.preview.map((item, i) => (
                    <li key={i}>
                      <details>
                        <summary>{item.question}</summary>
                        <p className="reading">{item.answer}</p>
                      </details>
                    </li>
                  ))}
                </ol>
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

            {data.updates.length > 0 && (
              <section className="card" aria-labelledby="whats-new">
                <h2 id="whats-new">{t("updates.title")}</h2>
                <ol className="update-list">
                  {data.updates.map((update) => (
                    <li key={update.id}>
                      <p className="update-head">
                        <strong>{update.version ? t("updates.version", { n: update.version }) : t("updates.announcement")}</strong>
                        <span className="hint">{dateTime(update.created_at)}</span>
                      </p>
                      <p className="reading">{update.note}</p>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {data.published_at && <Reviews listingId={listingId} isAuthor={data.is_mine} />}
          </>
        )}
      </QueryState>
    </div>
  );
}
