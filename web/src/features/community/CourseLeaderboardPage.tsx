import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { community, type Period, type Scope } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { BoardControls, LeaderboardList } from "./Leaderboard";

/** The XP earned in this one course by everyone who has it (the author and those who added it). */
export function CourseLeaderboardPage() {
  const { t } = useI18n();
  const { courseId = "" } = useParams();
  const [period, setPeriod] = useState<Period>("week");
  const [scope, setScope] = useState<Scope>("everyone");
  const key = ["community", "course-board", courseId] as const;
  const board = useQuery({ queryKey: [...key, period, scope], queryFn: () => community.courseLeaderboard(courseId, period, scope) });
  return (
    <div className="page community">
      <header className="page-header">
        <h1>{t("course.leaderboardTitle")}</h1>
        <p className="hint">{t("course.leaderboardIntro")}</p>
      </header>
      <BoardControls period={period} scope={scope} onPeriod={setPeriod} onScope={setScope} />
      <QueryState query={board}>
        {(data) => (
          <>
            {data.participants <= 1 ? (
              <p className="banner info">{t("course.leaderboardPrivate")}</p>
            ) : (
              <p className="hint">{t("course.leaderboardParticipants", { n: data.participants })}</p>
            )}
            <LeaderboardList board={data} queryKeys={[key]} />
          </>
        )}
      </QueryState>
    </div>
  );
}
