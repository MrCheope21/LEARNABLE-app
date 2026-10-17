import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { community, type Period, type Scope } from "../../api/endpoints";
import type { Schemas } from "../../api/client";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";
import { ErrorBanner } from "../../components/QueryState";

export const PERIODS: Period[] = ["day", "week", "month", "all"];
export const SCOPES: Scope[] = ["everyone", "friends"];

type Board = Schemas["Leaderboard"];
type Entry = Schemas["LeaderboardEntry"];

/** Day / week / month / all-time, and everyone / friends: the two switches over a leaderboard. */
export function BoardControls({ period, scope, onPeriod, onScope }: { period: Period; scope: Scope; onPeriod: (p: Period) => void; onScope: (s: Scope) => void }) {
  const { t } = useI18n();
  return (
    <div className="board-controls">
      <div role="group" aria-label={t("community.period")} className="segmented">
        {PERIODS.map((p) => (
          <button key={p} type="button" aria-pressed={period === p} onClick={() => onPeriod(p)}>
            {t(`community.period.${p}` as MessageKey)}
          </button>
        ))}
      </div>
      <div role="group" aria-label={t("community.scope")} className="segmented">
        {SCOPES.map((s) => (
          <button key={s} type="button" aria-pressed={scope === s} onClick={() => onScope(s)}>
            {t(`community.scope.${s}` as MessageKey)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The leader on top (linking to their profile), then everyone ranked, with the viewer marked. */
export function LeaderboardList({ board, queryKeys }: { board: Board; queryKeys: readonly (readonly unknown[])[] }) {
  const { t } = useI18n();
  const [leader] = board.entries;
  if (!leader) {
    return <p className="state">{board.scope === "friends" ? t("community.emptyFriends") : t("community.empty")}</p>;
  }
  return (
    <>
      <section className="card leader-card" aria-label={t("community.leader")}>
        <span className="leader-crown" aria-hidden="true">
          👑
        </span>
        <div>
          <span className="hint">{t("community.leader")}</span>
          <h2>
            <PersonLink entry={leader} />
          </h2>
          <p>{t("community.xp", { n: leader.xp.toLocaleString() })}</p>
        </div>
      </section>
      <ol className="board" aria-label={t("community.title")}>
        {board.entries.map((entry) => (
          <BoardRow key={entry.user_id} entry={entry} queryKeys={queryKeys} />
        ))}
      </ol>
      {board.me && !board.entries.some((e) => e.is_me) && (
        <p className="card board-me">
          {t("community.yourPlace")}: <strong>#{board.me.rank}</strong> · {t("community.xp", { n: board.me.xp.toLocaleString() })}
        </p>
      )}
      <p className="hint">{t("community.windowNote")}</p>
    </>
  );
}

function PersonLink({ entry }: { entry: Entry }) {
  const { t } = useI18n();
  return (
    <Link to={`/community/users/${entry.user_id}`}>
      {entry.name}
      {entry.is_me && <span className="pill"> {t("community.you")}</span>}
    </Link>
  );
}

function BoardRow({ entry, queryKeys }: { entry: Entry; queryKeys: readonly (readonly unknown[])[] }) {
  const { t } = useI18n();
  return (
    <li className={entry.is_me ? "board-row me" : "board-row"} value={entry.rank}>
      <span className="board-rank">{entry.rank}</span>
      <span className="board-name">
        <PersonLink entry={entry} />
      </span>
      <span className="board-xp">{t("community.xp", { n: entry.xp.toLocaleString() })}</span>
      {!entry.is_me && <FollowButton userId={entry.user_id} following={entry.following} refresh={queryKeys} />}
    </li>
  );
}

/** Follow / Following, refreshing whatever lists show the change. */
export function FollowButton({ userId, following, refresh }: { userId: string; following: boolean; refresh: readonly (readonly unknown[])[] }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => (following ? community.unfollow(userId) : community.follow(userId)),
    onSuccess: () => {
      for (const key of [...refresh, ["community"]]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
  return (
    <>
      <button type="button" className={following ? undefined : "primary"} aria-pressed={following} disabled={toggle.isPending} onClick={() => toggle.mutate()}>
        {following ? t("community.following") : t("community.follow")}
      </button>
      <ErrorBanner error={toggle.error} />
    </>
  );
}
