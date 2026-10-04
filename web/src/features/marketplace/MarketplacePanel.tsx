import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { marketplace } from "../../api/endpoints";
import { ErrorBanner } from "../../components/QueryState";
import { CATEGORIES, LEVELS, categoryLabel, levelLabel } from "./labels";

type Info = Schemas["ListingInfo"];
type MyListing = Schemas["MyListing"];

const EMPTY: Info = { title: "", subtitle: "", description: "", outcomes: [], audience: "", level: "all", category: "other", tags: [] };

function infoOf(listing: MyListing): Info {
  const { title, subtitle, description, outcomes, audience, level, category, tags } = listing;
  return { title, subtitle, description, outcomes, audience, level, category, tags };
}

/**
 * On a course page. Your own course: its Marketplace page (the "shop window" others see before
 * adding it), saved as a draft and published when you're ready. A course from the marketplace:
 * whose it is and what that means.
 */
export function MarketplacePanel({ courseId, courseTitle }: { courseId: string; courseTitle: string }) {
  const state = useQuery({ queryKey: ["course-marketplace", courseId], queryFn: () => marketplace.forCourse(courseId) });
  if (!state.data) return null;
  const { origin, listing } = state.data;
  if (origin) {
    return (
      <section className="card marketplace-origin" aria-label="From the marketplace">
        <h2>🛒 From the marketplace</h2>
        <p>
          Made by <strong>{origin.author}</strong> (version {origin.version}). Its author keeps the chapters, questions and answers up
          to date, so you can't edit them here: updates reach you automatically.
        </p>
        <p className="hint">
          Your study is your own: activating concepts, pausing, your answers, your review plan and XP, and the priority you give
          each question (only you see it).
        </p>
        <Link to={`/marketplace/${origin.listing_id}`}>See its marketplace page</Link>
      </section>
    );
  }
  return <SalesPage courseId={courseId} courseTitle={courseTitle} listing={listing ?? null} />;
}

function SalesPage({ courseId, courseTitle, listing }: { courseId: string; courseTitle: string; listing: MyListing | null }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<Info>(() => (listing ? infoOf(listing) : { ...EMPTY, title: courseTitle }));
  const [outcomes, setOutcomes] = useState(() => (info.outcomes ?? []).join("\n"));
  const [tags, setTags] = useState(() => (info.tags ?? []).join(", "));
  const [rights, setRights] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const ids = useId();

  const payload = (): Info => ({
    ...info,
    outcomes: outcomes
      .split("\n")
      .map((o) => o.trim())
      .filter(Boolean)
      .slice(0, 8),
    tags: tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .slice(0, 8),
  });
  const refresh = (updated: MyListing, message: string) => {
    queryClient.setQueryData(["course-marketplace", courseId], (old: Schemas["CourseMarketplace"] | undefined) => ({
      origin: old?.origin ?? null,
      listing: updated,
    }));
    void queryClient.invalidateQueries({ queryKey: ["marketplace"] });
    setNotice(message);
  };
  const save = useMutation({
    mutationFn: () => marketplace.saveInfo(courseId, payload()),
    onSuccess: (updated) => refresh(updated, updated.status === "PUBLISHED" ? "Saved: the marketplace page shows it now." : "Draft saved. Nobody else sees it until you publish."),
  });
  const publish = useMutation({
    mutationFn: () => marketplace.publish(courseId, { ...payload(), rights_confirmed: true }),
    onSuccess: (updated) =>
      refresh(
        updated,
        updated.version > 1
          ? `Published version ${updated.version}: everyone who has the course now gets your latest questions.`
          : "Published! Other users can now find it in the Marketplace.",
      ),
  });
  const unpublish = useMutation({
    mutationFn: () => marketplace.unpublish(listing!.id),
    onSuccess: (updated) => refresh(updated, "Unpublished: new people can't find it. Those who already have it keep it."),
  });
  const busy = save.isPending || publish.isPending || unpublish.isPending;
  const set = (patch: Partial<Info>) => setInfo((current) => ({ ...current, ...patch }));
  const valid = info.title.trim() && info.description.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) save.mutate();
  };

  const status = listing?.status ?? "NONE";
  return (
    <section className="card sales-page" aria-labelledby={`${ids}-title`}>
      <header className="card-header">
        <h2 id={`${ids}-title`}>🛒 Marketplace page</h2>
        <span className="pill">
          {status === "PUBLISHED" ? `Published · version ${listing!.version}` : status === "UNPUBLISHED" ? "Not published" : status === "DRAFT" ? "Draft" : "Not shared"}
        </span>
      </header>
      <p className="hint">
        Share this course with other users. Here you write its page, the only thing people see before adding it: what it covers, who
        it's for, what they'll learn. They also see the chapter titles and how many questions there are; the questions themselves
        only once they have it, and your uploaded material never.
      </p>
      {listing && status === "PUBLISHED" && (
        <p>
          <Link to={`/marketplace/${listing.id}`}>See it as others do</Link> · {listing.acquisition_count} students
        </p>
      )}
      {!open ? (
        <button type="button" className={listing ? undefined : "primary"} onClick={() => setOpen(true)}>
          {listing ? "Edit the marketplace page" : "Write a marketplace page"}
        </button>
      ) : (
        <form onSubmit={submit} className="sales-form">
          <label>
            Title
            <input value={info.title} maxLength={200} required onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label>
            Subtitle <span className="hint">(one line, e.g. "All 300 oral exam questions, with model answers")</span>
            <input value={info.subtitle} maxLength={200} onChange={(e) => set({ subtitle: e.target.value })} />
          </label>
          <div className="sales-row">
            <label>
              Category
              <select value={info.category} onChange={(e) => set({ category: e.target.value as Info["category"] })}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel[c]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Level
              <select value={info.level} onChange={(e) => set({ level: e.target.value as Info["level"] })}>
                {LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {levelLabel[l]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Description <span className="hint">(what it covers, how you made it, how to use it)</span>
            <textarea rows={6} value={info.description} maxLength={5000} required onChange={(e) => set({ description: e.target.value })} />
          </label>
          <label>
            What students will learn <span className="hint">(one per line, up to 8)</span>
            <textarea rows={4} value={outcomes} onChange={(e) => setOutcomes(e.target.value)} />
          </label>
          <label>
            Who it's for
            <textarea rows={2} value={info.audience} maxLength={1000} onChange={(e) => set({ audience: e.target.value })} />
          </label>
          <label>
            Tags <span className="hint">(comma separated, up to 8)</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" disabled={!valid || busy}>
              {save.isPending ? "Saving…" : status === "PUBLISHED" ? "Save page" : "Save draft"}
            </button>
            <button type="button" className="link" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <fieldset className="publish-box">
            <legend>{status === "PUBLISHED" ? "Publish an update" : "Publish"}</legend>
            <p className="hint">
              {status === "PUBLISHED"
                ? "Sends your current chapters, questions and answers to everyone who has the course. Their own progress is kept."
                : "Makes the course visible in the Marketplace. It's free for now. You can keep editing it and publish updates later."}
            </p>
            <label className="toggle">
              <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} />
              The questions and answers are mine to share (I wrote them, or I have the rights to the material they come from).
            </label>
            <div className="actions" style={{ marginTop: 0 }}>
              <button type="button" className="primary" disabled={!valid || !rights || busy} onClick={() => publish.mutate()}>
                {publish.isPending ? "Publishing…" : status === "PUBLISHED" ? "Publish update" : "Publish"}
              </button>
              {status === "PUBLISHED" && (
                <button type="button" className="link danger" disabled={busy} onClick={() => unpublish.mutate()}>
                  Unpublish
                </button>
              )}
            </div>
          </fieldset>
        </form>
      )}
      {notice && (
        <p className="banner info" role="status">
          {notice}
        </p>
      )}
      <ErrorBanner error={save.error ?? publish.error ?? unpublish.error} />
    </section>
  );
}
