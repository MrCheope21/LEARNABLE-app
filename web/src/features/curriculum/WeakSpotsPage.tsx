import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { dashboard } from "../../api/endpoints";
import { QueryState } from "../../components/QueryState";
import { HelpTip } from "../../components/HelpTip";
import { dateTime } from "../../components/labels";
import { weakSpotsKey } from "./CourseLayout";
import { CheckRow } from "../study/EvaluationView";
import { studyLink } from "../study/StudyPage";

const DRILL_CONCEPTS = 5;

/**
 * "What you keep getting wrong": the misconceptions the evaluator found in your last few
 * answers to each item, grouped by concept, with a practice session on exactly those concepts.
 */
export function WeakSpotsPage() {
  const { courseId = "" } = useParams();
  const spots = useQuery({ queryKey: weakSpotsKey(courseId), queryFn: () => dashboard.weakSpots(courseId) });
  return (
    <div className="page">
      <header className="page-header">
        <div className="title-row">
          <h1>What you keep getting wrong</h1>
          <HelpTip text="help.weakSpots" topic="What you keep getting wrong" guide="progress" />
        </div>
        <p className="hint">
          Mistakes found in your recent answers, by concept. They disappear once your latest answers to the item no
          longer show them. Practice doesn't change your review schedule.
        </p>
      </header>
      <QueryState query={spots} label="Looking at your recent answers…">
        {({ concepts }) =>
          concepts.length === 0 ? (
            <p className="state">No recurring mistakes right now. Keep answering and they will show up here.</p>
          ) : (
            <>
              <Link
                className="button primary"
                to={studyLink(courseId, "PRACTICE", {
                  conceptIds: concepts.slice(0, DRILL_CONCEPTS).map((c) => c.concept_id),
                })}
              >
                Practice the top {Math.min(concepts.length, DRILL_CONCEPTS)}{" "}
                {concepts.length === 1 ? "concept" : "concepts"}
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
                        Practice this
                      </Link>
                    </header>
                    <ul className="checklist">
                      {concept.misconceptions.map((m) => (
                        <CheckRow key={m.text} tone="bad" mark="!" word="Misconception">
                          {m.text}
                          <span className="hint">
                            {" "}
                            · seen {m.count} {m.count === 1 ? "time" : "times"}, last {dateTime(m.last_seen)}
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
