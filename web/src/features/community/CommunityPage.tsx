import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { community, type Period, type Scope } from "../../api/endpoints";
import type { Schemas } from "../../api/client";
import { meKey } from "../../app/AppShell";
import { auth } from "../../api/endpoints";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { BoardControls, FollowButton, LeaderboardList } from "./Leaderboard";

const BOARD_KEY = ["community", "board"] as const;
const PEOPLE_KEY = ["community", "people"] as const;

/** "Community": the leaderboard and, on the Friends tab, the people you follow. */
export function CommunityPage({ tab = "leaderboard" }: { tab?: "leaderboard" | "friends" }) {
  const { t } = useI18n();
  return (
    <div className="page community">
      <header className="page-header">
        <h1>{t("community.title")}</h1>
        <p className="hint">{t("community.intro")}</p>
      </header>
      <nav className="tabs" aria-label={t("community.title")}>
        <NavLink end to="/community">
          {t("community.tab.leaderboard")}
        </NavLink>
        <NavLink to="/community/friends">{t("community.tab.friends")}</NavLink>
      </nav>
      <JoinBanner />
      {tab === "friends" ? <FriendsTab /> : <GlobalBoard />}
    </div>
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
  const board = useQuery({ queryKey: [...BOARD_KEY, period, scope], queryFn: () => community.leaderboard(period, scope) });
  return (
    <>
      <BoardControls period={period} scope={scope} onPeriod={setPeriod} onScope={setScope} />
      <QueryState query={board}>{(data) => <LeaderboardList board={data} queryKeys={[BOARD_KEY]} />}</QueryState>
    </>
  );
}

/** The Friends tab: search, people you follow, your followers. */
export function FriendsTab() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const searchId = useId();
  const following = useQuery({ queryKey: [...PEOPLE_KEY, "following"], queryFn: community.following });
  const followers = useQuery({ queryKey: [...PEOPLE_KEY, "followers"], queryFn: community.followers });
  const found = useQuery({
    queryKey: [...PEOPLE_KEY, "search", submitted],
    queryFn: () => community.people(submitted),
    enabled: submitted.length >= 2,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(query.trim());
  };
  return (
    <>
      <form className="card friends-search" role="search" onSubmit={submit}>
        <label htmlFor={searchId}>{t("community.searchLabel")}</label>
        <div className="inline-field">
          <input id={searchId} type="search" value={query} maxLength={80} placeholder={t("community.searchPlaceholder")} onChange={(e) => setQuery(e.target.value)} />
          <button type="submit" disabled={query.trim().length < 2}>
            {t("community.search")}
          </button>
        </div>
        {submitted.length >= 2 && (
          <QueryState query={found}>
            {(people) => (people.length === 0 ? <p className="hint">{t("community.noResults")}</p> : <PeopleList people={people} />)}
          </QueryState>
        )}
      </form>
      <section className="card" aria-labelledby="following-title">
        <h2 id="following-title">{t("community.followingList")}</h2>
        <QueryState query={following}>
          {(people) => (people.length === 0 ? <p className="hint">{t("community.noFollowing")}</p> : <PeopleList people={people} />)}
        </QueryState>
      </section>
      <section className="card" aria-labelledby="followers-title">
        <h2 id="followers-title">{t("community.followersList")}</h2>
        <QueryState query={followers}>
          {(people) => (people.length === 0 ? <p className="hint">{t("community.noFollowers")}</p> : <PeopleList people={people} />)}
        </QueryState>
      </section>
    </>
  );
}

function PeopleList({ people }: { people: Schemas["Person"][] }) {
  const { t } = useI18n();
  return (
    <ul className="people">
      {people.map((p) => (
        <li key={p.user_id} className="person">
          <div>
            <Link to={`/community/users/${p.user_id}`}>{p.name}</Link>
            {p.i_follow && p.follows_me && <span className="pill"> {t("community.friend")}</span>}
            {!p.i_follow && p.follows_me && <span className="pill"> {t("community.followsYou")}</span>}
            <p className="hint">
              {t("community.streakDays", { n: p.streak })} · {t("community.xpToday", { n: p.xp_today })}
            </p>
          </div>
          <FollowButton userId={p.user_id} following={p.i_follow} refresh={[PEOPLE_KEY, BOARD_KEY]} />
        </li>
      ))}
    </ul>
  );
}

/** One learner's public page: name, XP, streak, followers, and follow. */
export function ProfilePage() {
  const { t } = useI18n();
  const { userId = "" } = useParams();
  const profile = useQuery({ queryKey: ["community", "profile", userId], queryFn: () => community.profile(userId), retry: false });
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
                {p.i_follow && p.follows_me && <span className="pill">{t("community.friend")}</span>}
                {!p.i_follow && p.follows_me && <span className="pill">{t("community.followsYou")}</span>}
              </div>
              <dl className="stats">
                <Stat label={t("community.statXpTotal")} value={p.xp_total.toLocaleString()} />
                <Stat label={t("community.statXpWeek")} value={p.xp_week.toLocaleString()} />
                <Stat label={t("community.statStreak")} value={String(p.streak)} />
                <Stat label={t("community.statFollowers")} value={String(p.followers)} />
                <Stat label={t("community.statFollowing")} value={String(p.following)} />
              </dl>
              {!p.is_me && <FollowButton userId={p.user_id} following={p.i_follow} refresh={[["community", "profile", userId], PEOPLE_KEY, BOARD_KEY]} />}
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
