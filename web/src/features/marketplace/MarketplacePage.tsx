import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { marketplace, type ListingFilters } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import {
  CATEGORIES,
  LEVELS,
  categoryIcon,
  categoryLabel,
  languageLabel,
  levelLabel,
  priceLabel,
  sizeLabel,
  sortLabel,
} from "./labels";

type Listing = Schemas["ListingSummary"];

/**
 * Courses other people published: browse by category, filter, open a course's page. What a course
 * contains is visible only once it's in your courses.
 */
export function MarketplacePage() {
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
        <h1>Marketplace</h1>
        <p className="hint">
          Courses made by other LEARNABLE users. Add one to your courses and study it with your own schedule: its author keeps it
          up to date. To share one of yours, open it and fill in its <em>Marketplace page</em>.
        </p>
      </header>

      <nav className="category-chips" aria-label="Categories">
        <button type="button" aria-pressed={!filters.category} onClick={() => set({ category: undefined })}>
          All
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
          Search courses
        </label>
        <input id={`${ids}-q`} type="search" placeholder="Search by title or description" value={search} maxLength={200} onChange={(e) => setSearch(e.target.value)} />
        <button type="submit">Search</button>
        <label>
          Level
          <select value={filters.level ?? ""} onChange={(e) => set({ level: (e.target.value || undefined) as ListingFilters["level"] })}>
            <option value="">Any</option>
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {levelLabel[l]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Language
          <select value={filters.language ?? ""} onChange={(e) => set({ language: e.target.value || undefined })}>
            <option value="">Any</option>
            {Object.entries(languageLabel).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Size
          <select value={filters.size ?? ""} onChange={(e) => set({ size: (e.target.value || undefined) as ListingFilters["size"] })}>
            <option value="">Any</option>
            {(Object.keys(sizeLabel) as (keyof typeof sizeLabel)[]).map((s) => (
              <option key={s} value={s}>
                {sizeLabel[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sort
          <select value={filters.sort ?? "popular"} onChange={(e) => set({ sort: e.target.value as ListingFilters["sort"] })}>
            {(Object.keys(sortLabel) as (keyof typeof sortLabel)[]).map((s) => (
              <option key={s} value={s}>
                {sortLabel[s]}
              </option>
            ))}
          </select>
        </label>
      </form>

      <QueryState query={listings} label="Loading courses…">
        {(rows) =>
          rows.length === 0 ? (
            <p className="state">No course matches these filters yet.</p>
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

function ListingCard({ listing }: { listing: Listing }) {
  return (
    <article className="card listing-card" aria-labelledby={`listing-${listing.id}`}>
      <span className="listing-category">
        {categoryIcon[listing.category]} {categoryLabel[listing.category]}
      </span>
      <Link id={`listing-${listing.id}`} className="listing-title" to={`/marketplace/${listing.id}`}>
        {listing.title}
      </Link>
      {listing.subtitle && <p className="listing-subtitle">{listing.subtitle}</p>}
      <p className="hint">by {listing.author}</p>
      <p className="listing-facts">
        {listing.item_count} questions · {listing.chapter_count} {listing.chapter_count === 1 ? "chapter" : "chapters"} ·{" "}
        {levelLabel[listing.level]} · {languageLabel[listing.language] ?? listing.language}
      </p>
      <div className="listing-foot">
        <strong>{priceLabel(listing)}</strong>
        {listing.course_id ? <span className="pill">In your courses</span> : <span className="hint">{listing.acquisition_count} students</span>}
      </div>
    </article>
  );
}
