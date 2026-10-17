import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { marketplace, type ListingFilters } from "../../api/endpoints";
import { HelpTip } from "../../components/HelpTip";
import { QueryState } from "../../components/QueryState";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";
import { CATEGORIES, LEVELS, categoryIcon } from "./labels";

const LANGUAGE_CODES = ["it", "en"];
const SIZES = ["small", "medium", "large"] as const;
const SORTS = ["popular", "newest", "largest"] as const;

type Listing = Schemas["ListingSummary"];

/**
 * Courses other people published: browse by category, filter, open a course's page. What a course
 * contains is visible only once it's in your courses.
 */
export function MarketplacePage() {
  const { t } = useI18n();
  const { categoryLabel, levelLabel, sizeLabel, sortLabel, languageName } = useLabels();
  const [filters, setFilters] = useState<ListingFilters>({ sort: "popular" });
  const [search, setSearch] = useState("");
  const listings = useQuery({
    queryKey: ["marketplace", filters],
    queryFn: () => marketplace.browse(filters),
    placeholderData: keepPreviousData,
  });
  const set = (patch: Partial<ListingFilters>) => setFilters((current) => ({ ...current, ...patch }));
  const ids = useId();

  return (
    <div className="page marketplace">
      <header className="page-header">
        <div className="title-row">
          <h1>{t("nav.marketplace")}</h1>
          <HelpTip text="help.marketplace" topic={t("nav.marketplace")} guide="marketplace" />
        </div>
        <p className="hint">{t("mkt.intro")}</p>
      </header>

      <PublishedByMe />

      <nav className="category-chips" aria-label={t("mkt.categories")}>
        <button type="button" aria-pressed={!filters.category} onClick={() => set({ category: undefined })}>
          {t("mkt.all")}
        </button>
        {CATEGORIES.map((c) => (
          <button key={c} type="button" aria-pressed={filters.category === c} onClick={() => set({ category: filters.category === c ? undefined : c })}>
            {categoryIcon[c]} {categoryLabel[c]}
          </button>
        ))}
      </nav>

      <form
        className="marketplace-filters"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          set({ q: search.trim() || undefined });
        }}
      >
        <label className="sr-only" htmlFor={`${ids}-q`}>
          {t("library.search")}
        </label>
        <input id={`${ids}-q`} type="search" placeholder={t("mkt.searchPlaceholder")} value={search} maxLength={200} onChange={(e) => setSearch(e.target.value)} />
        <button type="submit">{t("common.search")}</button>
        <label>
          {t("mkt.level")}
          <select value={filters.level ?? ""} onChange={(e) => set({ level: (e.target.value || undefined) as ListingFilters["level"] })}>
            <option value="">{t("mkt.any")}</option>
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {levelLabel[l]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("mkt.language")}
          <select value={filters.language ?? ""} onChange={(e) => set({ language: e.target.value || undefined })}>
            <option value="">{t("mkt.any")}</option>
            {LANGUAGE_CODES.map((code) => (
              <option key={code} value={code}>
                {languageName(code)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("mkt.size")}
          <select value={filters.size ?? ""} onChange={(e) => set({ size: (e.target.value || undefined) as ListingFilters["size"] })}>
            <option value="">{t("mkt.any")}</option>
            {SIZES.map((s) => (
              <option key={s} value={s}>
                {sizeLabel[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("mkt.sort")}
          <select value={filters.sort ?? "popular"} onChange={(e) => set({ sort: e.target.value as ListingFilters["sort"] })}>
            {SORTS.map((s) => (
              <option key={s} value={s}>
                {sortLabel[s]}
              </option>
            ))}
          </select>
        </label>
      </form>

      <QueryState query={listings} label={t("mkt.loading")}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="state">{t("mkt.noMatch")}</p>
          ) : (
            <ul className="listing-grid">
              {rows.map((listing) => (
                <li key={listing.id}>
                  <ListingCard listing={listing} />
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
    </div>
  );
}

/** The author's own listings: drafts, published and unpublished, with how many students. */
function PublishedByMe() {
  const { t } = useI18n();
  const { count } = useLabels();
  const mine = useQuery({ queryKey: ["marketplace", "mine"], queryFn: marketplace.mine });
  if (!mine.data?.length) return null;
  return (
    <details className="card published-by-me">
      <summary>
        <strong>{t("mkt.publishedByMe")}</strong> <span className="hint">({mine.data.length})</span>
      </summary>
      <ul>
        {mine.data.map((listing) => (
          <li key={listing.id}>
            {listing.status === "DRAFT" ? <span>{listing.title}</span> : <Link to={`/marketplace/${listing.id}`}>{listing.title}</Link>}
            <span className="hint">
              {t(`mkt.status.${listing.status}` as MessageKey)}
              {listing.version > 0 && ` · ${t("mkt.version", { n: listing.version })}`} · {count("mkt.students", listing.acquisition_count)}
            </span>
            {listing.source_course_id && <Link to={`/courses/${listing.source_course_id}`}>{t("mkt.editCourse")}</Link>}
          </li>
        ))}
      </ul>
    </details>
  );
}

function ListingCard({ listing }: { listing: Listing }) {
  const { t } = useI18n();
  const { categoryLabel, levelLabel, languageName, priceLabel, count } = useLabels();
  return (
    <article className="card listing-card" aria-labelledby={`listing-${listing.id}`}>
      <span className="listing-category">
        {categoryIcon[listing.category]} {categoryLabel[listing.category]}
      </span>
      <Link id={`listing-${listing.id}`} className="listing-title" to={`/marketplace/${listing.id}`}>
        {listing.title}
      </Link>
      {listing.subtitle && <p className="listing-subtitle">{listing.subtitle}</p>}
      <p className="hint">{t("mkt.by", { author: listing.author })}</p>
      <p className="listing-facts">
        {count("unit.question", listing.item_count)} · {count("unit.chapter", listing.chapter_count)} · {levelLabel[listing.level]} ·{" "}
        {languageName(listing.language)}
      </p>
      <div className="listing-foot">
        <strong>{priceLabel(listing)}</strong>
        {listing.course_id ? <span className="pill">{t("mkt.inYourCourses")}</span> : <span className="hint">{count("mkt.students", listing.acquisition_count)}</span>}
      </div>
    </article>
  );
}
