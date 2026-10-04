import { createContext, useContext } from "react";

/**
 * Whether the course on screen is read-only: one reached through the marketplace, whose content
 * its author keeps up to date. Editing controls hide themselves; studying, pausing and one's own
 * question priorities stay. (The server refuses content changes anyway.)
 */
const ReadOnlyCourse = createContext(false);

export const ReadOnlyCourseProvider = ReadOnlyCourse.Provider;

export function useReadOnlyCourse(): boolean {
  return useContext(ReadOnlyCourse);
}

/** Shown instead of drag handles in a read-only course. */
export const AUTHOR_ORDER = "The author sets the order of this course.";
