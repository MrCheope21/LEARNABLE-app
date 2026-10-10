import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { dashboard } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { HelpTip } from "../../components/HelpTip";
import { dateTime } from "../../components/labels";
import { useI18n } from "../../i18n";
import { weakSpotsKey } from "./CourseLayout";
import { CheckRow } from "../study/EvaluationView";
import { studyLink } from "../study/StudyPage";

const DRILL_CONCEPTS = 5;

/**
 * "What you keep getting wrong": the misconceptions the evaluator found in your last few
 * answers to each item, grouped by concept, with a practice session on exactly those concepts.
 */
export function WeakSpotsPage() {
  const { t } = useI18n();
  const { courseId = "" } = useParams();
  const spots = useQuery({ queryKey: weakSpotsKey(courseId), queryFn: () => dashboard.weakSpots(courseId) });
  return (
    <div className="page">
      <header className="page-header">
        <div className="title-row">
          <h1>{t("course.weakSpots")}</h1>
          <HelpTip text="help.weakSpots" topic={t("course.weakSpots")} guide="progress" />
        </div>
        <p className="hint">{t("weak.intro")}</p>
      </header>
      <QueryState query={spots} label={t("weak.loading")}>
        {({ concepts }) =>
          concepts.length === 0 ? (
            <p className="state">{t("weak.empty")}</p>
          ) : (
            <>
              <Link
                className="button primary"
                to={studyLink(courseId, "PRACTICE", {
                  conceptIds: concepts.slice(0, DRILL_CONCEPTS).map((c) => c.concept_id),
                })}
              >
                {t(concepts.length === 1 ? "weak.practiceTop.one" : "weak.practiceTop.other", { n: Math.min(concepts.length, DRILL_CONCEPTS) })}
              </Link>
              <ul className="weak-list">
                {concepts.map((concept) => (
                  <li key={concept.concept_id} className="card">
                    <header className="card-header">
                      <div>
                        <h2>
                          <Link to={`/courses/${courseId}/concepts/${concept.concept_id}`}>{concept.concept_title}</Link>
                        </h2>
                        <span className="hint">
                          {concept.chapter_title} · {concept.topic_title}
                        </span>
                      </div>
                      <Link className="button" to={studyLink(courseId, "PRACTICE", { conceptIds: [concept.concept_id] })}>
                        {t("weak.practiceThis")}
                      </Link>
                    </header>
                    <ul className="checklist">
                      {concept.misconceptions.map((m) => (
                        <CheckRow key={m.text} tone="bad" mark="!" word={t("eval.misconception")}>
                          {m.text}
                          <span className="hint">
                            {" "}
                            · {t(m.count === 1 ? "weak.seen.one" : "weak.seen.other", { n: m.count, date: dateTime(m.last_seen) })}
                          </span>
                        </CheckRow>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </>
          )
        }
      </QueryState>
    </div>
  );
}
