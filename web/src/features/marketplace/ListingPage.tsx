import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { marketplace } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { categoryIcon, categoryLabel, count, languageLabel, levelLabel, priceLabel } from "./labels";

/**
 * A course's marketplace page, as its author wrote it: what it covers, who it's for, what you'll
 * learn, and its size (chapters and question counts). The questions themselves show only once
 * the course is in your courses.
 */
export function ListingPage() {
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
        <Link to="/marketplace">← Marketplace</Link>
      </p>
      <QueryState query={listing} label="Loading course…">
        {(data) => (
          <>
            <header className="card listing-hero">
              <span className="listing-category">
                {categoryIcon[data.category]} {categoryLabel[data.category]}
              </span>
              <h1>{data.title}</h1>
              {data.subtitle && <p className="listing-subtitle">{data.subtitle}</p>}
              <p className="hint">
                by <strong>{data.author}</strong> · {levelLabel[data.level]} · {languageLabel[data.language] ?? data.language}
                {data.published_at && ` · updated ${dateTime(data.updated_at)}`}
              </p>
              <dl className="listing-stats">
                <div>
                  <dt>Questions</dt>
                  <dd>{data.item_count}</dd>
                </div>
                <div>
                  <dt>Chapters</dt>
                  <dd>{data.chapter_count}</dd>
                </div>
                <div>
                  <dt>Students</dt>
                  <dd>{data.acquisition_count}</dd>
                </div>
              </dl>
              <div className="actions">
                {data.is_mine ? (
                  <span className="pill">Your course{data.status !== "PUBLISHED" && ` · ${data.status === "DRAFT" ? "draft" : "not published"}`}</span>
                ) : data.course_id ? (
                  <Link className="button primary" to={`/courses/${data.course_id}`}>
                    Open in my courses
                  </Link>
                ) : (
                  <button type="button" className="primary" disabled={acquire.isPending} onClick={() => acquire.mutate()}>
                    {data.has_access ? "Add back to my courses" : `Add to my courses · ${priceLabel(data)}`}
                  </button>
                )}
              </div>
              <ErrorBanner error={acquire.error} />
            </header>

            <section className="card">
              <h2>About this course</h2>
              <p className="reading listing-description">{data.description}</p>
            </section>

            {data.outcomes.length > 0 && (
              <section className="card">
                <h2>What you'll learn</h2>
                <ul className="outcomes">
                  {data.outcomes.map((o, i) => (
                    <li key={i}>{o}</li>
                  ))}
                </ul>
              </section>
            )}

            {data.audience && (
              <section className="card">
                <h2>Who it's for</h2>
                <p className="reading">{data.audience}</p>
              </section>
            )}

            <section className="card">
              <h2>Chapters</h2>
              <ol className="listing-chapters">
                {data.chapters.map((chapter, i) => (
                  <li key={i}>
                    <span>{chapter.title}</span>
                    <span className="hint">{count(chapter.questions, "question", "questions")}</span>
                  </li>
                ))}
              </ol>
              <p className="hint">
                The questions and answers become visible once the course is in your courses. You study them inside LEARNABLE: the
                author's material can't be downloaded.
              </p>
            </section>
          </>
        )}
      </QueryState>
    </div>
  );
}
