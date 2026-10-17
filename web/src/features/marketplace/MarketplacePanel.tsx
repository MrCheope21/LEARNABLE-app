import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { marketplace } from "../../api/endpoints";
import { ErrorBanner } from "../../components/QueryState";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import { CATEGORIES, LEVELS } from "./labels";

export const MARKETPLACE_ANCHOR = "#marketplace-page";

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
  const { t } = useI18n();
  const state = useQuery({ queryKey: ["course-marketplace", courseId], queryFn: () => marketplace.forCourse(courseId) });
  if (!state.data) return null;
  const { origin, listing } = state.data;
  if (origin) {
    return (
      <section className="card marketplace-origin" aria-label={t("sales.originTitle")}>
        <h2>{t("sales.originTitle")}</h2>
        <p>{t("sales.madeBy", { author: origin.author, version: origin.version })}</p>
        <p className="hint">{t("sales.yourStudy")}</p>
        <Link to={`/marketplace/${origin.listing_id}`}>{t("sales.seePage")}</Link>
      </section>
    );
  }
  return <SalesPage courseId={courseId} courseTitle={courseTitle} listing={listing ?? null} />;
}

function SalesPage({ courseId, courseTitle, listing }: { courseId: string; courseTitle: string; listing: MyListing | null }) {
  const { t } = useI18n();
  const { categoryLabel, levelLabel, count } = useLabels();
  const queryClient = useQueryClient();
  // "Publish to the marketplace" links here (#marketplace-page): open the editor and show it.
  const { hash } = useLocation();
  const [open, setOpen] = useState(hash === MARKETPLACE_ANCHOR);
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    if (hash === MARKETPLACE_ANCHOR) section.current?.scrollIntoView({ block: "start" });
  }, [hash]);
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
    onSuccess: (updated) => refresh(updated, updated.status === "PUBLISHED" ? t("sales.noteSaved") : t("sales.noteDraft")),
  });
  const publish = useMutation({
    mutationFn: () => marketplace.publish(courseId, { ...payload(), rights_confirmed: true }),
    onSuccess: (updated) =>
      refresh(
        updated,
        updated.version > 1
          ? t("sales.notePublishedV", { n: updated.version })
          : t("sales.notePublished"),
      ),
  });
  const unpublish = useMutation({
    mutationFn: () => marketplace.unpublish(listing!.id),
    onSuccess: (updated) => refresh(updated, t("sales.noteUnpublished")),
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
    <section ref={section} id="marketplace-page" className="card sales-page" aria-labelledby={`${ids}-title`}>
      <header className="card-header">
        <h2 id={`${ids}-title`}>{t("sales.title")}</h2>
        <span className="pill">
          {status === "PUBLISHED" ? t("sales.pPublished", { n: listing!.version }) : status === "UNPUBLISHED" ? t("sales.pNot") : status === "DRAFT" ? t("sales.pDraft") : t("sales.pNone")}
        </span>
      </header>
      <p className="hint">{t("sales.explain")}</p>
      {listing && status === "PUBLISHED" && (
        <p>
          <Link to={`/marketplace/${listing.id}`}>{t("sales.seeAsOthers")}</Link> · {count("mkt.students", listing.acquisition_count)}
        </p>
      )}
      {!open ? (
        <button type="button" className={listing ? undefined : "primary"} onClick={() => setOpen(true)}>
          {listing ? t("sales.edit") : t("sales.write")}
        </button>
      ) : (
        <form onSubmit={submit} className="sales-form">
          <label>
            {t("common.title")}
            <input value={info.title} maxLength={200} required onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label>
            {t("sales.subtitle")} <span className="hint">{t("sales.subtitleHint")}</span>
            <input value={info.subtitle} maxLength={200} onChange={(e) => set({ subtitle: e.target.value })} />
          </label>
          <div className="sales-row">
            <label>
              {t("sales.category")}
              <select value={info.category} onChange={(e) => set({ category: e.target.value as Info["category"] })}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel[c]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("mkt.level")}
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
            {t("sales.description")} <span className="hint">{t("sales.descriptionHint")}</span>
            <textarea rows={6} value={info.description} maxLength={5000} required onChange={(e) => set({ description: e.target.value })} />
          </label>
          <label>
            {t("sales.outcomes")} <span className="hint">{t("sales.outcomesHint")}</span>
            <textarea rows={4} value={outcomes} onChange={(e) => setOutcomes(e.target.value)} />
          </label>
          <label>
            {t("mkt.audience")}
            <textarea rows={2} value={info.audience} maxLength={1000} onChange={(e) => set({ audience: e.target.value })} />
          </label>
          <label>
            {t("sales.tags")} <span className="hint">{t("sales.tagsHint")}</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" disabled={!valid || busy}>
              {save.isPending ? t("common.saving") : status === "PUBLISHED" ? t("sales.savePage") : t("sales.saveDraft")}
            </button>
            <button type="button" className="link" onClick={() => setOpen(false)}>
              {t("common.close")}
            </button>
          </div>
          <fieldset className="publish-box">
            <legend>{status === "PUBLISHED" ? t("sales.publishUpdate") : t("sales.publish")}</legend>
            <p className="hint">
              {status === "PUBLISHED" ? t("sales.publishHintUpdate") : t("sales.publishHint")}
            </p>
            <label className="toggle">
              <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} />
              {t("sales.rights")}
            </label>
            <div className="actions" style={{ marginTop: 0 }}>
              <button type="button" className="primary" disabled={!valid || !rights || busy} onClick={() => publish.mutate()}>
                {publish.isPending ? t("sales.publishing") : status === "PUBLISHED" ? t("sales.publishUpdateBtn") : t("sales.publish")}
              </button>
              {status === "PUBLISHED" && (
                <button type="button" className="link danger" disabled={busy} onClick={() => unpublish.mutate()}>
                  {t("sales.unpublish")}
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
