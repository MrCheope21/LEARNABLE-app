import { useQuery } from "@tanstack/react-query";
import { dashboard } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { ActivityCalendar } from "./Widgets";

/** "See more": a year of study activity. */
export function ActivityPage() {
  const { t } = useI18n();
  const activity = useQuery({ queryKey: ["activity", 52], queryFn: () => dashboard.activity(52) });
  return (
    <div className="page">
      <header className="page-header">
        <h1>{t("activity.title")}</h1>
        <p className="hint">{t("activity.pageIntro")}</p>
      </header>
      <section className="card">
        <QueryState query={activity}>{(data) => <ActivityCalendar activity={data} large />}</QueryState>
      </section>
    </div>
  );
}
