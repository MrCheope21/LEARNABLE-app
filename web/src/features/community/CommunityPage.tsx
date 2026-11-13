import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { community, courses, type Period, type Scope } from "../../api/endpoints";
import type { Schemas } from "../../api/client";
import { meKey } from "../../app/AppShell";
import { auth } from "../../api/endpoints";
import { Icon } from "../../components/Icon";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { ReportButton } from "../../components/ReportButton";
import { useI18n } from "../../i18n";
import { badge, useInbox } from "../notifications/useInbox";
import { MessagesTab } from "./ChatPage";
import { BoardControls, FriendButton, LeaderboardList } from "./Leaderboard";

const BOARD_KEY = ["community", "board"] as const;
const PEOPLE_KEY = ["community", "people"] as const;

type Tab = "leaderboard" | "friends" | "messages";

/** "Community": the leaderboard, your friends and friend requests, and your messages. */
export function CommunityPage({ tab = "leaderboard" }: { tab?: Tab }) {
  const { t } = useI18n();
  const inbox = useInbox();
  return (
    <div className="page community">
      <div className="page-header">
        <h1>{t("community.title")}</h1>
        <p className="hint">{t("community.intro")}</p>
      </div>
      <nav className="tabs" aria-label={t("community.title")}>
        <NavLink end to="/community">
          {t("community.tab.leaderboard")}
        </NavLink>
        <NavLink to="/community/friends">
          {t("community.tab.friends")}
          <Count n={inbox.friend_requests} label={t("friends.badge", { n: inbox.friend_requests })} />
        </NavLink>
        <NavLink to="/community/messages">
          {t("community.tab.messages")}
          <Count n={inbox.messages} label={t("chat.badge", { n: inbox.messages })} />
        </NavLink>
      </nav>
      <JoinBanner />
      {tab === "friends" ? <FriendsTab /> : tab === "messages" ? <MessagesTab /> : <GlobalBoard />}
    </div>
  );
}

function Count({ n, label }: { n: number; label: string }) {
  if (n <= 0) return null;
  return (
    <span className="count-badge" aria-label={label} role="img">
      {badge(n)}
    </span>
  );
}

/** Opt in to the community from the page that needs it. */
function JoinBanner() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  const join = useMutation({
    mutationFn: () => auth.updateMe({ community_visible: true }),
    onSuccess: (user) => {
      queryClient.setQueryData(meKey, user);
      void queryClient.invalidateQueries({ queryKey: ["community"] });
    },
  });
  if (!me.data || me.data.community_visible) return null;
  return (
    <section className="card join-card" aria-labelledby="join-title">
      <h2 id="join-title">{t("community.joinTitle")}</h2>
      <p>{t("community.joinText")}</p>
      {me.data.display_name ? (
        <button type="button" className="primary" disabled={join.isPending} onClick={() => join.mutate()}>
          {t("community.joinButton")}
        </button>
      ) : (
        <p className="banner warning">
          {t("community.needName")} <Link to="/settings">{t("account.settings")}</Link>
        </p>
      )}
      <ErrorBanner error={join.error} />
    </section>
  );
}

export function GlobalBoard() {
  const [period, setPeriod] = useState<Period>("week");
  const [scope, setScope] = useState<Scope>("everyone");
  // "" = XP from every course; otherwise the XP earned in that one course.
  const [courseId, setCourseId] = useState("");
  const { t } = useI18n();
  const mine = useQuery({ queryKey: ["courses"], queryFn: courses.list });
  const board = useQuery({
    queryKey: [...BOARD_KEY, period, scope, courseId],
    queryFn: () => (courseId ? community.courseLeaderboard(courseId, period, scope) : community.leaderboard(period, scope)),
  });
  return (
    <>
      <BoardControls period={period} scope={scope} onPeriod={setPeriod} onScope={setScope} />
      {(mine.data?.length ?? 0) > 0 && (
        <label className="inline-form board-course">
          {t("community.boardCourse")}
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            <option value="">{t("community.allCourses")}</option>
            {mine.data?.map((course) => (
              <option key={course.id} value={course.id}>
                {course.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {courseId && <p className="hint">{t("community.boardCourseHint")}</p>}
      <QueryState query={board}>{(data) => <LeaderboardList board={data} queryKeys={[BOARD_KEY]} />}</QueryState>
    </>
  );
}

/** The Friends tab: requests waiting for you first, then search, your friends, requests you sent. */
export function FriendsTab() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const searchId = useId();
  const friends = useQuery({ queryKey: [...PEOPLE_KEY, "friends"], queryFn: community.friends });
  const requests = useQuery({ queryKey: [...PEOPLE_KEY, "requests"], queryFn: community.requests, refetchInterval: 30_000 });
  const found = useQuery({
    queryKey: [...PEOPLE_KEY, "search", submitted],
    queryFn: () => community.people(submitted),
    enabled: submitted.length >= 2,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(query.trim());
  };
  const incoming = requests.data?.incoming ?? [];
  const outgoing = requests.data?.outgoing ?? [];
  return (
    <>
      {incoming.length > 0 && (
        <section className="card requests-card" aria-labelledby="incoming-title">
          <h2 id="incoming-title">
            {t("friends.incoming")} <span className="count-badge">{incoming.length}</span>
          </h2>
          <PeopleList people={incoming} />
        </section>
      )}
      <form className="card friends-search" role="search" onSubmit={submit}>
        <label htmlFor={searchId}>{t("community.searchLabel")}</label>
        <div className="inline-field">
          <input id={searchId} type="search" value={query} maxLength={80} placeholder={t("community.searchPlaceholder")} onChange={(e) => setQuery(e.target.value)} />
          <button type="submit" disabled={query.trim().length < 2}>
            {t("community.search")}
          </button>
        </div>
        <p className="hint">{t("friends.searchHint")}</p>
        {submitted.length >= 2 && (
          <QueryState query={found}>
            {(people) => (people.length === 0 ? <p className="banner info">{t("friends.searchHelp")}</p> : <PeopleList people={people} />)}
          </QueryState>
        )}
      </form>
      <MyLink />
      <section className="card" aria-labelledby="friends-title">
        <h2 id="friends-title">{t("friends.yours")}</h2>
        <QueryState query={friends}>
          {(people) => (people.length === 0 ? <p className="hint">{t("friends.none")}</p> : <PeopleList people={people} />)}
        </QueryState>
      </section>
      {outgoing.length > 0 && (
        <section className="card" aria-labelledby="outgoing-title">
          <h2 id="outgoing-title">{t("friends.outgoing")}</h2>
          <p className="hint">{t("friends.outgoingHint")}</p>
          <PeopleList people={outgoing} />
        </section>
      )}
    </>
  );
}

/** "Add me": the address of your own profile, to send to a friend. Needs a username or the community. */
function MyLink() {
  const { t } = useI18n();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  const [copied, setCopied] = useState(false);
  if (!me.data) return null;
  if (!me.data.username && !me.data.community_visible) {
    return (
      <p className="card hint">
        {t("friends.linkNeedsName")} <Link to="/settings">{t("account.settings")}</Link>
      </p>
    );
  }
  const link = `${window.location.origin}/community/users/${me.data.id}`;
  const copy = async () => {
    try {
      if (navigator.share) await navigator.share({ title: "Recallable", text: t("friends.linkText"), url: link });
      else {
        await navigator.clipboard.writeText(link);
        setCopied(true);
      }
    } catch {
      // Cancelled, or no clipboard: the link stays selectable below.
    }
  };
  return (
    <section className="card my-link" aria-labelledby="my-link-title">
      <h2 id="my-link-title">{t("friends.linkTitle")}</h2>
      <p className="hint">
        {t("friends.linkHint")}
        {me.data.username && ` ${t("friends.linkUsername", { name: me.data.username })}`}
      </p>
      <div className="inline-field">
        <input readOnly value={link} aria-label={t("friends.linkTitle")} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="primary" onClick={() => void copy()}>
          {copied ? t("admin.copied") : t("friends.linkShare")}
        </button>
      </div>
    </section>
  );
}

function PeopleList({ people }: { people: Schemas["Person"][] }) {
  const { t } = useI18n();
  return (
    <ul className="people">
      {people.map((p) => (
        <li key={p.user_id} className="person">
          <span className="profile-avatar" aria-hidden="true">
            {p.name[0]?.toUpperCase()}
          </span>
          <div className="person-main">
            <Link to={`/community/users/${p.user_id}`}>{p.name}</Link>
            <p className="hint">
              {p.relation === "request_received"
                ? t("friends.wantsYou")
                : p.relation === "request_sent"
                  ? t("friends.waiting")
                  : `${t("community.streakDays", { n: p.streak })} · ${t("community.xpToday", { n: p.xp_today })}`}
            </p>
          </div>
          <span className="person-actions">
            {p.relation === "friends" && (
              <Link className="button" to={`/community/messages/${p.user_id}`}>
                <Icon name="chat" size={16} /> {t("chat.write")}
              </Link>
            )}
            <FriendButton userId={p.user_id} relation={p.relation} refresh={[PEOPLE_KEY, BOARD_KEY]} />
          </span>
        </li>
      ))}
    </ul>
  );
}

/** One learner's public page: name, XP, streak, friends, and what you can do about them. */
export function ProfilePage() {
  const { t } = useI18n();
  const { userId = "" } = useParams();
  const queryClient = useQueryClient();
  const key = ["community", "profile", userId];
  const profile = useQuery({ queryKey: key, queryFn: () => community.profile(userId), retry: false });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["community"] });
  const block = useMutation({ mutationFn: () => community.block(userId), onSuccess: refresh });
  const unblock = useMutation({ mutationFn: () => community.unblock(userId), onSuccess: refresh });
  return (
    <div className="page community">
      <p className="breadcrumbs">
        <Link to="/community">← {t("community.title")}</Link>
      </p>
      {profile.isError ? (
        <p className="state">{t("community.notFound")}</p>
      ) : (
        <QueryState query={profile}>
          {(p) => (
            <section className="card profile-card" aria-labelledby="profile-name">
              <span className="profile-avatar large" aria-hidden="true">
                {p.name[0]?.toUpperCase()}
              </span>
              <div>
                <h1 id="profile-name">
                  {p.name}
                  {p.is_me && <span className="pill"> {t("community.you")}</span>}
                </h1>
                <p className="hint">{t("community.since", { date: new Date(p.member_since).toLocaleDateString() })}</p>
                {p.relation === "friends" && <span className="pill friend-pill">{t("community.friend")}</span>}
                {p.relation === "request_received" && <span className="pill">{t("friends.wantsYou")}</span>}
                {p.relation === "request_sent" && <span className="pill">{t("friends.waiting")}</span>}
              </div>
              <dl className="stats">
                <Stat label={t("community.statXpTotal")} value={p.xp_total.toLocaleString()} />
                <Stat label={t("community.statXpWeek")} value={p.xp_week.toLocaleString()} />
                <Stat label={t("community.statStreak")} value={String(p.streak)} />
                <Stat label={t("friends.stat")} value={String(p.friends)} />
              </dl>
              {!p.is_me && (
                <div className="profile-actions">
                  {p.blocked ? (
                    <>
                      <p className="banner warning">{t("friends.blockedNote")}</p>
                      <button type="button" disabled={unblock.isPending} onClick={() => unblock.mutate()}>
                        {t("friends.unblock")}
                      </button>
                    </>
                  ) : (
                    <>
                      {p.relation === "friends" && (
                        <Link className="button primary" to={`/community/messages/${p.user_id}`}>
                          <Icon name="chat" size={16} /> {t("chat.write")}
                        </Link>
                      )}
                      <FriendButton userId={p.user_id} relation={p.relation} refresh={[key, PEOPLE_KEY, BOARD_KEY]} />
                      <button
                        type="button"
                        className="link danger"
                        disabled={block.isPending}
                        onClick={() => {
                          if (window.confirm(t("friends.blockConfirm", { name: p.name }))) block.mutate();
                        }}
                      >
                        {t("friends.block")}
                      </button>
                    </>
                  )}
                  <ReportButton kind="user" targetId={p.user_id} />
                  <ErrorBanner error={block.error ?? unblock.error} />
                </div>
              )}
            </section>
          )}
        </QueryState>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
