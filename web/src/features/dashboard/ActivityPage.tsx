import { useQuery } from "@tanstack/react-query";
import { dashboard } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { ActivityCalendar } from "./Widgets";

/** "See more": a year of study activity. */
export function ActivityPage() {
  const activity = useQuery({ queryKey: ["activity", 52], queryFn: () => dashboard.activity(52) });
  return (
    <div className="page">
      <header className="page-header">
        <h1>Activity</h1>
        <p className="hint">
          Completed answers per day over the last year, in your timezone. An answer counts once it has a final grade,
          whether it was right or wrong.
        </p>
      </header>
      <section className="card">
        <QueryState query={activity}>{(data) => <ActivityCalendar activity={data} large />}</QueryState>
      </section>
    </div>
  );
}
