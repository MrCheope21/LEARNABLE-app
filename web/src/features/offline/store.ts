import type { Schemas } from "../../api/client";
import { review } from "../../api/endpoints";

/**
 * Courses kept on this device for reviewing without a network, and the answers given offline
 * that still have to reach the server. Both live in localStorage (a pack of a few hundred
 * questions is well under its limit); everything here survives a reload and works offline.
 */
export type Pack = Schemas["OfflinePack"];
export type QueuedAnswer = Schemas["OfflineAnswer"] & { course_id: string };

const PACKS = "recallable.offline.packs";
const QUEUE = "recallable.offline.queue";
const listeners = new Set<() => void>();

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    listeners.forEach((listener) => listener());
    return true;
  } catch {
    return false; // storage full or blocked
  }
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function packs(): Record<string, Pack> {
  return read<Record<string, Pack>>(PACKS, {});
}

export function packOf(courseId: string): Pack | null {
  return packs()[courseId] ?? null;
}

/** Downloads (or refreshes) a course's pack. False when the device has no room for it. */
export async function download(courseId: string): Promise<boolean> {
  const pack = await review.offlinePack(courseId);
  return write(PACKS, { ...packs(), [courseId]: pack });
}

export function forget(courseId: string): void {
  const next = packs();
  delete next[courseId];
  write(PACKS, next);
}

export function queue(): QueuedAnswer[] {
  return read<QueuedAnswer[]>(QUEUE, []);
}

/** Questions already answered offline (and not yet sent) are not asked again. */
export function answeredIds(courseId: string): Set<string> {
  return new Set(queue().filter((a) => a.course_id === courseId).map((a) => a.learning_item_id));
}

export function enqueue(answer: Omit<QueuedAnswer, "client_id" | "answered_at">): void {
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  write(QUEUE, [...queue(), { ...answer, client_id: id.replace(/[^A-Za-z0-9_-]/g, ""), answered_at: new Date().toISOString() }]);
}

let syncing: Promise<number> | null = null;

/**
 * Sends the queued answers, course by course. Sent ones leave the queue whether they were
 * applied or skipped (the server decides, and a resend is harmless). Returns how many were
 * applied; on a network error the rest stays queued for next time.
 */
export function sync(): Promise<number> {
  syncing ??= (async () => {
    let applied = 0;
    try {
      const byCourse = new Map<string, QueuedAnswer[]>();
      for (const answer of queue()) byCourse.set(answer.course_id, [...(byCourse.get(answer.course_id) ?? []), answer]);
      for (const [courseId, answers] of byCourse) {
        try {
          const result = await review.offlineSync(
            courseId,
            answers.map(({ course_id: _unused, ...rest }) => rest),
          );
          applied += result.applied;
          const sent = new Set(answers.map((a) => a.client_id));
          write(QUEUE, queue().filter((a) => !sent.has(a.client_id)));
          // The schedule moved: the pack's due dates are stale, refresh it while online.
          if (packOf(courseId)) await download(courseId).catch(() => undefined);
        } catch {
          // Offline again, or the server refused: keep them for the next try.
        }
      }
    } finally {
      syncing = null;
    }
    return applied;
  })();
  return syncing;
}
