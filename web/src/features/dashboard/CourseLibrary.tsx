import { useMutation, useQueryClient } from "@tanstack/react-query";
import { HelpTip } from "../../components/HelpTip";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { courses } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { ErrorBanner } from "../../components/QueryState";
import {
  CourseCover,
  LearnButton,
  Metric,
  ReviewButton,
  type CourseCardData,
} from "../courses/CourseParts";

type Status = "all" | "in_progress" | "not_started" | "due" | "completed";
type Sort = "recent_study" | "recent_created" | "alphabetical" | "most_due";

const STATUS_LABEL: Record<Status, string> = {
  all: "All courses",
  in_progress: "In progress",
  not_started: "Not started",
  due: "Reviews due",
  completed: "Nothing new to learn",
};
const SORT_LABEL: Record<Sort, string> = {
  recent_study: "Recently studied",
  recent_created: "Recently created",
  alphabetical: "Alphabetical",
  most_due: "Most reviews due",
};

function statusOf(card: CourseCardData): Exclude<Status, "all" | "due">[] {
  const statuses: Exclude<Status, "all" | "due">[] = [];
  if (card.items_introduced === 0) statuses.push("not_started");
  else statuses.push("in_progress");
  if (card.learn.kind === "none" && card.items_trained > 0) statuses.push("completed");
  return statuses;
}

function matches(card: CourseCardData, status: Status): boolean {
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
export function CourseLibrary({ cards, heading = "My courses" }: { cards: CourseCardData[]; heading?: string }) {
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
          <h2 id="library-heading">{heading}</h2>
          <HelpTip text="help.courses" topic={heading} guide="structure" />
        </div>
        <span className="hint">
          {shown.length === cards.length ? `${cards.length} ${cards.length === 1 ? "course" : "courses"}` : `${shown.length} of ${cards.length} shown`}
        </span>
      </div>
      <div className="toolbar">
        <label className="sr-only" htmlFor={searchId}>
          Search courses
        </label>
        <input id={searchId} type="search" placeholder="Search courses" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="sr-only" htmlFor={statusId}>
          Show
        </label>
        <select id={statusId} value={status} onChange={(e) => setStatus(e.target.value as Status)}>
          {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor={sortId}>
          Sort by
        </label>
        <select id={sortId} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          {(Object.keys(SORT_LABEL) as Sort[]).map((s) => (
            <option key={s} value={s}>
              {SORT_LABEL[s]}
            </option>
          ))}
        </select>
        <button type="button" className="primary new-course" aria-expanded={creating} onClick={() => setCreating((v) => !v)}>
          + New course
        </button>
        <Link className="button" to="/marketplace">
          🛒 Marketplace
        </Link>
      </div>
      {creating && <NewCourseForm onDone={() => setCreating(false)} />}
      {cards.length === 0 ? (
        !creating && (
          <div className="card state">
            <p>No courses yet. Create one, then add your study material or your own questions and answers.</p>
            <button type="button" className="primary" onClick={() => setCreating(true)}>
              Create your first course
            </button>
          </div>
        )
      ) : shown.length === 0 ? (
        <p className="state">No course matches this search or filter.</p>
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
          <span className="pill marketplace-pill" title="Its author keeps the content up to date; your study is your own.">
            🛒 From the marketplace · by {card.marketplace_author}
          </span>
        )}
        {card.description && <p className="course-description">{card.description}</p>}
        {next && (
          <p className="course-next">
            {card.learn.kind === "resume" ? "Continue" : "Next"}: <strong>{next.title}</strong>
          </p>
        )}
        {card.paused && <span className="pill warning">Paused</span>}
        <Metric done={card.concepts_studied} total={card.concepts_total} label="concepts studied" />
        <Metric done={card.items_introduced} total={card.items_trained} label="learning items introduced" />
      </div>
      <div className="course-actions">
        <CardMenu courseId={card.id} title={card.title} fromMarketplace={Boolean(card.marketplace_author)} />
        <ReviewButton courseId={card.id} due={card.due_now} />
        <LearnButton courseId={card.id} learn={card.learn} />
      </div>
    </article>
  );
}

function CardMenu({ courseId, title, fromMarketplace }: { courseId: string; title: string; fromMarketplace: boolean }) {
  const [open, setOpen] = useState(false);
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
      <button type="button" aria-haspopup="true" aria-expanded={open} aria-label={`More for ${title}`} onClick={() => setOpen((v) => !v)}>
        ⋯
      </button>
      {open && (
        <ul>
          <li>
            <Link to={`/courses/${courseId}`}>Course details</Link>
          </li>
          {!fromMarketplace && (
            <li>
              <Link to={`/courses/${courseId}/material`}>Study material</Link>
            </li>
          )}
          <li>
            <Link to="/progress">Progress</Link>
          </li>
        </ul>
      )}
    </div>
  );
}

function NewCourseForm({ onDone }: { onDone: () => void }) {
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
    <form className="card new-course-form" onSubmit={submit} aria-label="New course">
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required autoFocus />
      </label>
      <label>
        Language of the material
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="it">Italian</option>
          <option value="en">English</option>
        </select>
      </label>
      <button type="submit" className="primary" disabled={!title.trim() || create.isPending}>
        Create course
      </button>
      <ErrorBanner error={create.error} />
    </form>
  );
}
