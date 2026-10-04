import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { studyLink } from "../study/StudyPage";

export type CourseCardData = Schemas["CourseCard"];

// Calm, readable hues for placeholder covers (white initials meet contrast on each).
const COVER_HUES = ["#1555DD", "#0F766E", "#7C3AED", "#B45309", "#BE185D", "#15803D", "#1D4ED8", "#9333EA"];

function hash(value: string): number {
  let h = 0;
  for (const ch of value) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

export function initials(title: string): string {
  const words = title.trim().split(/\s+/).filter((w) => /\p{L}|\p{N}/u.test(w));
  const letters = words.slice(0, 2).map((w) => [...w].find((c) => /\p{L}|\p{N}/u.test(c)) ?? "");
  return letters.join("").toUpperCase() || "·";
}

/** A course cover: courses have no uploaded cover yet, so a consistent initials tile. */
export function CourseCover({ id, title, to }: { id: string; title: string; to?: string }) {
  const style = { background: COVER_HUES[hash(id) % COVER_HUES.length] };
  const content = <span aria-hidden="true">{initials(title)}</span>;
  if (to) {
    return (
      <Link to={to} className="course-cover" style={style} tabIndex={-1} aria-hidden="true">
        {content}
      </Link>
    );
  }
  return (
    <div className="course-cover" style={style} aria-hidden="true">
      {content}
    </div>
  );
}

/** "12 / 30 concepts studied" with a thin bar. Denominator 0 shows the count without a bar. */
export function Metric({ done, total, label }: { done: number; total: number; label: string }) {
  const share = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="metric">
      <span className="metric-label">
        <b>{done.toLocaleString()}</b> / {total.toLocaleString()} {label}
      </span>
      {total > 0 && (
        <div className="bar" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <span style={{ width: `${share}%` }} />
        </div>
      )}
    </div>
  );
}

export function learnTarget(courseId: string, learn: CourseCardData["learn"]): { to: string | null; label: string; hint: string } {
  switch (learn.kind) {
    case "resume":
      return {
        to: learn.session_id ? `/study/${courseId}?session=${learn.session_id}` : null,
        label: "Resume practice",
        hint: "Continue the round you left unfinished",
      };
    case "study":
      return {
        to: learn.concept ? `/courses/${courseId}/concepts/${learn.concept.id}` : null,
        label: "Learn next",
        hint: learn.concept ? `Study ${learn.concept.title}` : "Learn new material",
      };
    case "activate":
      return {
        to: learn.concept ? `/courses/${courseId}/concepts/${learn.concept.id}` : null,
        label: "Start learning",
        hint: learn.concept ? `Prepare the questions of ${learn.concept.title} and start studying it` : "Start studying the next concept",
      };
    case "setup":
      return { to: `/courses/${courseId}`, label: "Add material", hint: "Add study material or your own questions to start" };
    case "none":
      return { to: null, label: "All learned ✓", hint: "Everything in this course has been learned" };
  }
}

export function LearnButton({ courseId, learn }: { courseId: string; learn: CourseCardData["learn"] }) {
  const target = learnTarget(courseId, learn);
  if (!target.to) {
    return (
      <span className="button learn" aria-disabled="true" title={target.hint}>
        {target.label}
      </span>
    );
  }
  return (
    <Link className="button learn" to={target.to} title={target.hint}>
      {target.label}
    </Link>
  );
}

export function ReviewButton({ courseId, due }: { courseId: string; due: number }) {
  if (due <= 0) {
    return (
      <span className="no-due" title="Nothing in this course needs reviewing right now">
        ✓ Nothing to review now
      </span>
    );
  }
  return (
    <Link
      className="button review"
      to={studyLink(courseId, "SCHEDULED_REVIEW")}
      aria-label={`Review ${due} ${due === 1 ? "item" : "items"}`}
    >
      Review <span className="count-badge">{due.toLocaleString()}</span>
    </Link>
  );
}
