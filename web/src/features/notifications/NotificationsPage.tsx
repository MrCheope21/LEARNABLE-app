import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { notifications } from "../../api/endpoints";
import { Icon, type IconName } from "../../components/Icon";
import { QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";
import { inboxKey } from "./useInbox";

type Item = Schemas["NotificationRead"];

const ICONS: Record<string, IconName> = {
  friend_request: "community",
  friend_accepted: "community",
  course_update: "book",
  course_announcement: "chat",
  course_review: "star",
  review_reply: "chat",
  course_sold: "cart",
};

/** What happened while you were away: friend requests, course updates, reviews, sales. */
export function NotificationsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["notifications"], queryFn: notifications.list });
  const markRead = useMutation({
    mutationFn: () => notifications.markRead(),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: inboxKey }),
  });
  // Opening the page reads them: the badge clears, the rows stay marked as new until you leave.
  const unread = list.data?.unread ?? 0;
  const { mutate } = markRead;
  useEffect(() => {
    if (unread > 0) mutate();
  }, [unread, mutate]);
  return (
    <div className="page notifications-page">
      <div className="page-header">
        <h1>{t("notif.title")}</h1>
      </div>
      <QueryState query={list}>
        {(data) =>
          data.items.length === 0 ? (
            <p className="state">{t("notif.empty")}</p>
          ) : (
            <ul className="card notif-list">
              {data.items.map((item) => (
                <NotificationRow key={item.id} item={item} />
              ))}
            </ul>
          )
        }
      </QueryState>
    </div>
  );
}

function NotificationRow({ item }: { item: Item }) {
  const { t } = useI18n();
  const data = item.data as Record<string, string | number | null | undefined>;
  const who = item.actor ?? t("notif.someone");
  const known = `notif.kind.${item.kind}` in KNOWN;
  const text = known
    ? t(`notif.kind.${item.kind}` as MessageKey, {
        who,
        title: String(data.title ?? ""),
        n: String(data.version ?? data.rating ?? ""),
        amount: money(data.amount_cents, data.currency),
      })
    : t("notif.kind.other");
  const detail = String(data.note ?? data.message ?? "");
  const body = (
    <>
      <span className="notif-icon" aria-hidden="true">
        <Icon name={ICONS[item.kind] ?? "bell"} size={18} />
      </span>
      <span className="notif-text">
        <span>{text}</span>
        {detail && <span className="notif-detail">{detail}</span>}
        <span className="hint">{dateTime(item.created_at)}</span>
      </span>
      {!item.read && <span className="notif-dot" aria-label={t("notif.new")} role="img" />}
    </>
  );
  return <li className={item.read ? "notif" : "notif unread"}>{item.link ? <Link to={item.link}>{body}</Link> : <div>{body}</div>}</li>;
}

const KNOWN: Record<string, true> = {
  "notif.kind.friend_request": true,
  "notif.kind.friend_accepted": true,
  "notif.kind.course_update": true,
  "notif.kind.course_announcement": true,
  "notif.kind.course_review": true,
  "notif.kind.review_reply": true,
  "notif.kind.course_sold": true,
};

function money(cents: unknown, currency: unknown): string {
  if (typeof cents !== "number") return "";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: String(currency || "EUR") }).format(cents / 100);
  } catch {
    return (cents / 100).toFixed(2);
  }
}
