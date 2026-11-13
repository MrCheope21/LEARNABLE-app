import { useQuery } from "@tanstack/react-query";
import { dashboard } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { QueryState } from "../../components/QueryState";
import { useI18n } from "../../i18n";
import { CourseLibrary } from "../dashboard/CourseLibrary";

/** Every course, with the same cards, filters and create entry point as the dashboard. */
export function CoursesPage() {
  const { t } = useI18n();
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <div className="page">
      <h1 className="sr-only">{t("nav.courses")}</h1>
      <QueryState query={data} label={t("mkt.loading")}>
        {(d) => <CourseLibrary cards={d.courses} heading={t("libStatus.all")} />}
      </QueryState>
    </div>
  );
}
