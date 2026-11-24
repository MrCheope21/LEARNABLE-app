import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { Schemas } from "../../api/client";
import { admin, auth, marketplace } from "../../api/endpoints";
import { meKey } from "../../app/AppShell";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { StarInput, Stars } from "../../components/Stars";
import { useLabels } from "../../components/useLabels";
import { ReportButton } from "../../components/ReportButton";
import { useI18n } from "../../i18n";

type Review = Schemas["ListingReview"];

/**
 * Stars and comments from people who have the course. Whoever has it writes one review (and can
 * edit or delete it); the author answers; an administrator can remove one.
 */
export function Reviews({ listingId, isAuthor }: { listingId: string; isAuthor: boolean }) {
  const { t } = useI18n();
  const { count } = useLabels();
  const queryClient = useQueryClient();
  const key = ["listing", listingId, "reviews"];
  const reviews = useQuery({ queryKey: key, queryFn: () => marketplace.reviews(listingId) });
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["listing", listingId] });
    void queryClient.invalidateQueries({ queryKey: ["marketplace"] });
  };
  return (
    <section className="card reviews" aria-labelledby="reviews-title">
      <h2 id="reviews-title">{t("review.title")}</h2>
      <QueryState query={reviews}>
        {(data) => (
          <>
            {data.average !== null && data.average !== undefined ? (
              <div className="review-summary">
                <div className="review-average">
                  <strong>{data.average.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</strong>
                  <Stars value={data.average} size={18} />
                  <span className="hint">{count("review.count", data.count)}</span>
                </div>
                <ol className="review-bars" aria-label={t("review.distribution")}>
                  {[5, 4, 3, 2, 1].map((stars) => {
                    const n = data.distribution[stars - 1] ?? 0;
                    return (
                      <li key={stars}>
                        <span>{stars}</span>
                        <span className="review-bar" aria-hidden="true">
                          <span style={{ width: `${data.count ? (n / data.count) * 100 : 0}%` }} />
                        </span>
                        <span className="hint">{n}</span>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : (
              <p className="hint">{t("review.noReviews")}</p>
            )}
            {data.can_review && <ReviewForm key={data.mine?.updated_at ?? "new"} listingId={listingId} mine={data.mine ?? null} onDone={refresh} />}
            {!data.can_review && !isAuthor && <p className="hint">{t("review.needCourse")}</p>}
            <ul className="review-list">
              {data.items.map((review) => (
                <ReviewItem key={review.id} review={review} isAuthor={isAuthor} isAdmin={Boolean(me.data?.is_admin)} onDone={refresh} />
              ))}
            </ul>
          </>
        )}
      </QueryState>
    </section>
  );
}

function ReviewForm({ listingId, mine, onDone }: { listingId: string; mine: Review | null; onDone: () => void }) {
  const { t } = useI18n();
  const [rating, setRating] = useState(mine?.rating ?? 0);
  const [comment, setComment] = useState(mine?.comment ?? "");
  const [open, setOpen] = useState(!mine);
  const save = useMutation({
    mutationFn: () => marketplace.writeReview(listingId, { rating, comment: comment.trim() }),
    onSuccess: () => {
      setOpen(false);
      onDone();
    },
  });
  const remove = useMutation({ mutationFn: () => marketplace.deleteReview(listingId), onSuccess: onDone });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (rating > 0) save.mutate();
  };
  if (!open) {
    return (
      <p className="review-mine">
        {t("review.yours")}{" "}
        <button type="button" className="link" onClick={() => setOpen(true)}>
          {t("review.edit")}
        </button>
      </p>
    );
  }
  return (
    <form className="review-form" onSubmit={submit}>
      <h3>{mine ? t("review.editTitle") : t("review.write")}</h3>
      <StarInput value={rating} onChange={setRating} label={t("review.rating")} />
      <label>
        {t("review.comment")} <span className="hint">{t("review.commentHint")}</span>
        <textarea rows={3} value={comment} maxLength={2000} onChange={(e) => setComment(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" className="primary" disabled={rating === 0 || save.isPending}>
          {save.isPending ? t("common.saving") : mine ? t("common.save") : t("review.publish")}
        </button>
        {mine && (
          <>
            <button type="button" className="link" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </button>
            <button
              type="button"
              className="link danger"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(t("review.deleteConfirm"))) remove.mutate();
              }}
            >
              {t("review.delete")}
            </button>
          </>
        )}
      </div>
      <ErrorBanner error={save.error ?? remove.error} />
    </form>
  );
}

function ReviewItem({ review, isAuthor, isAdmin, onDone }: { review: Review; isAuthor: boolean; isAdmin: boolean; onDone: () => void }) {
  const { t } = useI18n();
  const [replying, setReplying] = useState(false);
  const [reply, setReply] = useState(review.reply);
  const answer = useMutation({
    mutationFn: () => marketplace.replyToReview(review.id, reply.trim()),
    onSuccess: () => {
      setReplying(false);
      onDone();
    },
  });
  const moderate = useMutation({ mutationFn: () => admin.deleteReview(review.id), onSuccess: onDone });
  return (
    <li className="review-item">
      <div className="review-head">
        <strong>{review.author}</strong>
        {review.is_mine && <span className="pill">{t("community.you")}</span>}
        <Stars value={review.rating} />
        <span className="hint">{new Date(review.updated_at).toLocaleDateString(undefined, { dateStyle: "medium" })}</span>
      </div>
      {review.comment && <p className="reading">{review.comment}</p>}
      {review.reply && !replying && (
        <blockquote className="review-reply">
          <strong>{t("review.authorReply")}</strong>
          <p>{review.reply}</p>
        </blockquote>
      )}
      {replying && (
        <form
          className="review-reply-form"
          onSubmit={(e) => {
            e.preventDefault();
            answer.mutate();
          }}
        >
          <label>
            {t("review.replyLabel")}
            <textarea rows={2} value={reply} maxLength={2000} onChange={(e) => setReply(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" className="primary" disabled={answer.isPending}>
              {t("common.save")}
            </button>
            <button type="button" className="link" onClick={() => setReplying(false)}>
              {t("common.cancel")}
            </button>
          </div>
        </form>
      )}
      <div className="review-tools">
        {isAuthor && !replying && (
          <button type="button" className="link" onClick={() => setReplying(true)}>
            {review.reply ? t("review.editReply") : t("review.reply")}
          </button>
        )}
        {!review.is_mine && <ReportButton kind="review" targetId={review.id} />}
        {isAdmin && !review.is_mine && (
          <button
            type="button"
            className="link danger"
            disabled={moderate.isPending}
            onClick={() => {
              if (window.confirm(t("review.moderateConfirm"))) moderate.mutate();
            }}
          >
            {t("review.moderate")}
          </button>
        )}
      </div>
      <ErrorBanner error={answer.error ?? moderate.error} />
    </li>
  );
}
