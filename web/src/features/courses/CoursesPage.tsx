import { useQuery } from "@tanstack/react-query";
import { dashboard } from "../../api/endpoints";
import { dashboardKey } from "../../app/AppShell";
import { QueryState } from "../../components/QueryState";
import { CourseLibrary } from "../dashboard/CourseLibrary";

/** Every course, with the same cards, filters and create entry point as the dashboard. */
export function CoursesPage() {
  const data = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  return (
    <div className="page">
      <h1 className="sr-only">Courses</h1>
      <QueryState query={data} label="Loading courses…">
        {(d) => <CourseLibrary cards={d.courses} heading="All courses" />}
      </QueryState>
    </div>
  );
}
