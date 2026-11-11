import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { chat, community } from "../../api/endpoints";
import { Icon } from "../../components/Icon";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { inboxKey } from "../notifications/useInbox";

const CHATS_KEY = ["chats"] as const;
const MAX_LENGTH = 2000;

type Message = Schemas["ChatMessage"];

/** "14:32" today, "Mon 14:32" this week, a date before that. */
function when(iso: string): string {
  const date = new Date(iso);
  const days = (Date.now() - date.getTime()) / 86_400_000;
  if (new Date().toDateString() === date.toDateString()) return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (days < 6) return date.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** The Messages tab: your chats, the latest first, then friends you haven't written to yet. */
export function MessagesTab() {
  const { t } = useI18n();
  const chats = useQuery({ queryKey: CHATS_KEY, queryFn: chat.list, refetchInterval: 15_000 });
  const friends = useQuery({ queryKey: ["community", "people", "friends"], queryFn: community.friends });
  const started = new Set((chats.data ?? []).map((c) => c.user_id));
  const fresh = (friends.data ?? []).filter((f) => !started.has(f.user_id));
  return (
    <>
      <QueryState query={chats}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="state">{fresh.length > 0 ? t("chat.noneYet") : t("chat.noFriends")}</p>
          ) : (
            <ul className="card chat-list">
              {rows.map((row) => (
                <li key={row.user_id}>
                  <Link to={`/community/messages/${row.user_id}`} className={row.unread > 0 ? "chat-row unread" : "chat-row"}>
                    <span className="profile-avatar" aria-hidden="true">
                      {row.name[0]?.toUpperCase()}
                    </span>
                    <span className="chat-row-main">
                      <span className="chat-row-top">
                        <strong>{row.name}</strong>
                        <span className="hint">{when(row.last_at)}</span>
                      </span>
                      <span className="chat-preview">
                        {row.last_mine && `${t("chat.you")}: `}
                        {row.last_message}
                      </span>
                    </span>
                    {row.unread > 0 && (
                      <span className="count-badge" role="img" aria-label={t("chat.badge", { n: row.unread })}>
                        {row.unread > 9 ? "9+" : row.unread}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
      {fresh.length > 0 && (
        <section className="card" aria-labelledby="chat-start">
          <h2 id="chat-start">{t("chat.start")}</h2>
          <ul className="chat-start-list">
            {fresh.map((f) => (
              <li key={f.user_id}>
                <Link className="button" to={`/community/messages/${f.user_id}`}>
                  <Icon name="chat" size={16} /> {f.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="hint">{t("chat.rules")}</p>
    </>
  );
}

/** One chat: the messages (yours on the right), older ones on request, and the box to write. */
export function ChatThreadPage() {
  const { t } = useI18n();
  const { userId = "" } = useParams();
  const queryClient = useQueryClient();
  const key = ["chat", userId];
  const thread = useQuery({ queryKey: key, queryFn: () => chat.thread(userId), refetchInterval: 5_000, retry: false });
  const [older, setOlder] = useState<Message[]>([]);
  const [noMore, setNoMore] = useState(false);
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const messages = [...older, ...(thread.data?.messages ?? [])];
  const lastId = messages[messages.length - 1]?.id;

  // Reading a chat clears its unread count: let the badges know.
  useEffect(() => {
    if (thread.data) {
      void queryClient.invalidateQueries({ queryKey: inboxKey });
      void queryClient.invalidateQueries({ queryKey: CHATS_KEY });
    }
  }, [lastId, thread.data, queryClient]);
  // Stay at the latest message when one arrives.
  useLayoutEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [lastId]);

  const send = useMutation({
    mutationFn: (body: string) => chat.send(userId, body),
    onSuccess: () => {
      setText("");
      void queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: CHATS_KEY });
    },
  });
  const loadOlder = useMutation({
    mutationFn: () => chat.thread(userId, messages[0]!.id),
    onSuccess: (page) => {
      setOlder((current) => [...page.messages, ...current]);
      if (!page.has_more) setNoMore(true);
    },
  });
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const body = text.trim();
    if (body && !send.isPending) send.mutate(body);
  };
  // Enter sends, Shift+Enter makes a new line (not while composing Japanese or Chinese text).
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="page chat-page">
      <p className="breadcrumbs">
        <Link to="/community/messages">← {t("community.tab.messages")}</Link>
      </p>
      {thread.isError ? (
        <p className="state">{t("chat.unavailable")}</p>
      ) : (
        <QueryState query={thread}>
          {(data) => (
            <section className="card chat" aria-labelledby="chat-with">
              <header className="chat-header">
                <span className="profile-avatar" aria-hidden="true">
                  {data.name[0]?.toUpperCase()}
                </span>
                <h1 id="chat-with">
                  <Link to={`/community/users/${data.user_id}`}>{data.name}</Link>
                </h1>
              </header>
              <div className="chat-messages" role="log" aria-live="polite" aria-label={t("chat.log", { name: data.name })} tabIndex={0}>
                {data.has_more && !noMore && messages.length > 0 && (
                  <button type="button" className="link chat-older" disabled={loadOlder.isPending} onClick={() => loadOlder.mutate()}>
                    {t("chat.older")}
                  </button>
                )}
                {messages.length === 0 && <p className="hint chat-empty">{t("chat.empty", { name: data.name })}</p>}
                {messages.map((m, i) => (
                  <Bubble key={m.id} message={m} showTime={i === messages.length - 1 || messages[i + 1]!.mine !== m.mine} />
                ))}
                <div ref={bottom} />
              </div>
              {data.can_send ? (
                <form className="chat-form" onSubmit={submit}>
                  <label className="sr-only" htmlFor="chat-text">
                    {t("chat.placeholder")}
                  </label>
                  <textarea id="chat-text" rows={1} value={text} maxLength={MAX_LENGTH} placeholder={t("chat.placeholder")} onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} />
                  <button type="submit" className="primary chat-send" disabled={!text.trim() || send.isPending} aria-label={t("chat.send")}>
                    <Icon name="send" size={18} />
                  </button>
                </form>
              ) : (
                <p className="banner info">{t("chat.closed")}</p>
              )}
              <ErrorBanner error={send.error ?? loadOlder.error} />
            </section>
          )}
        </QueryState>
      )}
    </div>
  );
}

function Bubble({ message, showTime }: { message: Message; showTime: boolean }) {
  const { t } = useI18n();
  return (
    <div className={message.mine ? "bubble-row mine" : "bubble-row"}>
      <p className="bubble">{message.body}</p>
      {showTime && (
        <span className="hint bubble-time">
          {when(message.created_at)}
          {message.mine && message.read && ` · ${t("chat.read")}`}
        </span>
      )}
    </div>
  );
}
