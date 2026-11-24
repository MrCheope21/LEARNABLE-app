import { useQuery } from "@tanstack/react-query";
import { notifications } from "../../api/endpoints";

export const inboxKey = ["inbox"] as const;

/** The counts behind the badges (unread notifications, unread messages, friend requests),
 * checked again every half minute and whenever the window gets the focus back. */
export function useInbox() {
  const inbox = useQuery({ queryKey: inboxKey, queryFn: notifications.inbox, refetchInterval: 30_000, staleTime: 10_000 });
  return inbox.data ?? { notifications: 0, messages: 0, friend_requests: 0 };
}

/** "9+" past nine: a badge has room for one character and a plus. */
export function badge(n: number): string {
  return n > 9 ? "9+" : String(n);
}
