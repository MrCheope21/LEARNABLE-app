import { useMutation, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { courses } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { ErrorBanner } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { useLabels } from "../../components/useLabels";
import type { MessageKey } from "../../i18n/messages/en";
import {
  CourseCover,
  LearnButton,
  Metric,
  ReviewButton,
  type CourseCardData,
} from "../courses/CourseParts";

type Status = "all" | "in_progress" | "not_started" | "due" | "completed" | "paused" | "archived";
type Sort = "recent_study" | "recent_created" | "alphabetical" | "most_due";

const STATUSES: Status[] = ["all", "in_progress", "not_started", "due", "completed", "paused", "archived"];
const SORTS: Sort[] = ["recent_study", "recent_created", "alphabetical", "most_due"];

function statusOf(card: CourseCardData): Exclude<Status, "all" | "due">[] {
  const statuses: Exclude<Status, "all" | "due">[] = [];
  if (card.items_introduced === 0) statuses.push("not_started");
  else statuses.push("in_progress");
  if (card.learn.kind === "none" && card.items_trained > 0) statuses.push("completed");
  return statuses;
}

function matches(card: CourseCardData, status: Status): boolean {
  // Archived courses are put away: only the "Archived" view shows them.
  if (status === "archived") return card.archived_at != null;
  if (card.archived_at != null) return false;
  if (status === "paused") return card.paused;
  if (status === "all") return true;
  if (status === "due") return card.due_now > 0;
  return statusOf(card).includes(status);
}

const compare: Record<Sort, (a: CourseCardData, b: CourseCardData) => number> = {
  recent_study: (a, b) => (b.last_studied_at ?? "").localeCompare(a.last_studied_at ?? "") || b.created_at.localeCompare(a.created_at),
  recent_created: (a, b) => b.created_at.localeCompare(a.created_at),
  alphabetical: (a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
  most_due: (a, b) => b.due_now - a.due_now || a.title.localeCompare(b.title),
};

/** "My courses": search, status filter, sorting, create, and one wide card per course. */
export function CourseLibrary({ cards, heading }: { cards: CourseCardData[]; heading?: string }) {
  const { t } = useI18n();
  const title = heading ?? t("library.heading");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status>("all");
  const [sort, setSort] = useState<Sort>("recent_study");
  const [creating, setCreating] = useState(false);
  const searchId = useId();
  const statusId = useId();
  const sortId = useId();

  const shown = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return cards
      .filter((c) => matches(c, status))
      .filter((c) => !needle || c.title.toLocaleLowerCase().includes(needle) || c.description.toLocaleLowerCase().includes(needle))
      .sort(compare[sort]);
  }, [cards, query, status, sort]);

  return (
    <section className="library" aria-labelledby="library-heading">
      <div className="library-header">
        <div className="title-row">
          <h2 id="library-heading">{title}</h2>
          <HelpTip text="help.courses" topic={title} guide="structure" />
        </div>
        <span className="hint">
          {shown.length === cards.length ? t(cards.length === 1 ? "library.count.one" : "library.count.other", { n: cards.length }) : t("library.shownOf", { shown: shown.length, total: cards.length })}
        </span>
      </div>
      <div className="toolbar">
        <label className="sr-only" htmlFor={searchId}>
          {t("library.search")}
        </label>
        <input id={searchId} type="search" placeholder={t("library.search")} value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="sr-only" htmlFor={statusId}>
          {t("library.show")}
        </label>
        <select id={statusId} value={status} onChange={(e) => setStatus(e.target.value as Status)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`libStatus.${s}` as MessageKey)}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor={sortId}>
          {t("library.sortBy")}
        </label>
        <select id={sortId} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {t(`libSort.${s}` as MessageKey)}
            </option>
          ))}
        </select>
        <button type="button" className="primary new-course" aria-expanded={creating} onClick={() => setCreating((v) => !v)}>
          {t("library.new")}
        </button>
        <Link className="button" to="/marketplace">
          {t("library.marketplace")}
        </Link>
      </div>
      {creating && <NewCourseForm onDone={() => setCreating(false)} />}
      {cards.length === 0 ? (
        !creating && (
          <div className="card state">
            <p>{t("library.empty")}</p>
            <button type="button" className="primary" onClick={() => setCreating(true)}>
              {t("library.createFirst")}
            </button>
          </div>
        )
      ) : shown.length === 0 ? (
        <p className="state">{t("library.noMatch")}</p>
      ) : (
        <ul className="course-list">
          {shown.map((card) => (
            <li key={card.id}>
              <CourseCardView card={card} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CourseCardView({ card }: { card: CourseCardData }) {
  const { t } = useI18n();
  const courseUrl = `/courses/${card.id}`;
  const next = card.learn.concept;
  return (
    <article className="card course-card" aria-labelledby={`course-${card.id}`}>
      <CourseCover id={card.id} title={card.title} to={courseUrl} />
      <div className="course-body">
        <Link id={`course-${card.id}`} className="course-title" to={courseUrl}>
          {card.title}
        </Link>
        {card.marketplace_author && (
          <span className="pill marketplace-pill" title={t("card.marketplaceHint")}>
            {t("card.marketplacePill", { author: card.marketplace_author })}
          </span>
        )}
        {card.description && <p className="course-description">{card.description}</p>}
        {next && (
          <p className="course-next">
            {card.learn.kind === "resume" ? t("card.continue") : t("card.next")}: <strong>{next.title}</strong>
          </p>
        )}
        {card.archived_at ? <span className="pill">{t("card.archived")}</span> : card.paused && <span className="pill warning">{t("card.paused")}</span>}
        <Metric done={card.concepts_studied} total={card.concepts_total} label={t("card.conceptsStudied")} />
        <Metric done={card.items_introduced} total={card.items_trained} label={t("card.itemsIntroduced")} />
      </div>
      <div className="course-actions">
        <CardMenu card={card} />
        <ReviewButton courseId={card.id} due={card.due_now} />
        <LearnButton courseId={card.id} learn={card.learn} />
      </div>
    </article>
  );
}

function CardMenu({ card }: { card: CourseCardData }) {
  const { t } = useI18n();
  const { id: courseId, title } = card;
  const fromMarketplace = Boolean(card.marketplace_author);
  const archived = card.archived_at != null;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const refresh = () => {
    setOpen(false);
    void queryClient.invalidateQueries({ queryKey: dashboardKey });
    void queryClient.invalidateQueries({ queryKey: ["courses"] });
  };
  const pause = useMutation({ mutationFn: () => courses.setPaused(courseId, !card.paused), onSuccess: refresh });
  const archive = useMutation({ mutationFn: () => courses.setArchived(courseId, !archived), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => courses.remove(courseId), onSuccess: refresh });
  const confirmDelete = () => {
    if (window.confirm(t(fromMarketplace ? "menu.confirmMarketplace" : "menu.confirmOwn", { title }))) remove.mutate();
  };
  const busy = pause.isPending || archive.isPending || remove.isPending;
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div className="card-menu" ref={menu}>
      <button type="button" aria-haspopup="true" aria-expanded={open} aria-label={t("card.moreFor", { title })} onClick={() => setOpen((v) => !v)}>
        ⋯
      </button>
      {open && (
        <ul>
          <li>
            <Link to={`/courses/${courseId}`}>{t("menu.details")}</Link>
          </li>
          {!fromMarketplace && (
            <li>
              <Link to={`/courses/${courseId}/material`}>{t("menu.material")}</Link>
            </li>
          )}
          <li>
            <Link to="/progress">{t("menu.progress")}</Link>
          </li>
          {!fromMarketplace && (
            <li>
              <Link to={`/courses/${courseId}#marketplace-page`}>{t("menu.publish")}</Link>
            </li>
          )}
          {!archived && (
            <li>
              <button type="button" disabled={busy} onClick={() => pause.mutate()}>
                {card.paused ? t("menu.resume") : t("menu.pause")}
              </button>
            </li>
          )}
          <li>
            <button type="button" disabled={busy} onClick={() => archive.mutate()}>
              {archived ? t("menu.restore") : t("menu.archive")}
            </button>
          </li>
          <li>
            <button type="button" className="danger" disabled={busy} onClick={confirmDelete}>
              {t("menu.delete")}
            </button>
          </li>
        </ul>
      )}
      <ErrorBanner error={pause.error ?? archive.error ?? remove.error} />
    </div>
  );
}

function NewCourseForm({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const { languageName } = useLabels();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("it");
  const create = useMutation({
    mutationFn: () => courses.create({ title: title.trim(), description: "", language }),
    onSuccess: (course) => {
      void queryClient.invalidateQueries({ queryKey: ["courses"] });
      void queryClient.invalidateQueries({ queryKey: dashboardKey });
      onDone();
      navigate(`/courses/${course.id}`);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim()) create.mutate();
  };
  return (
    <form className="card new-course-form" onSubmit={submit} aria-label={t("newCourse.aria")}>
      <label>
        {t("common.title")}
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required autoFocus />
      </label>
      <label>
        {t("newCourse.language")}
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="it">{languageName("it")}</option>
          <option value="en">{languageName("en")}</option>
        </select>
      </label>
      <button type="submit" className="primary" disabled={!title.trim() || create.isPending}>
        {t("newCourse.create")}
      </button>
      <ErrorBanner error={create.error} />
    </form>
  );
}
