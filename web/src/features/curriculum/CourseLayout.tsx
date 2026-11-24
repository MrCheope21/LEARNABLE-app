import { useQuery, type QueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { courses } from "../../api/endpoints";
import { CollapseToggle, useCollapsed } from "../../components/Collapsible";
import { ReadOnlyCourseProvider } from "../../components/CourseAccess";
import { QueryState } from "../../components/QueryState";
import { useLabels } from "../../components/useLabels";
import { useI18n } from "../../i18n";

export const outlineKey = (courseId: string) => ["outline", courseId] as const;
export const courseProgressKey = (courseId: string) => ["progress", courseId] as const;
export const weakSpotsKey = (courseId: string) => ["weak-spots", courseId] as const;

/** After a rename: every view that shows a course, chapter, topic or concept title. */
export function refreshTitles(queryClient: QueryClient, courseId: string) {
  for (const key of [outlineKey(courseId), courseProgressKey(courseId), ["course", courseId], ["course-summary", courseId], ["concept"], ["dashboard"], ["courses"]]) {
    void queryClient.invalidateQueries({ queryKey: key });
  }
}

/**
 * A Course workspace: the whole curriculum tree stays visible on the left while you work on
 * one Chapter, Topic or Concept on the right (desktop-first, docs/WEB_ARCHITECTURE.md §5).
 */
export function CourseLayout() {
  const { courseId = "", chapterId, topicId, conceptId } = useParams();
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => courses.get(courseId) });
  const tree = useCollapsed(`learnable.tree-collapsed.${courseId}`);
  // Topics start closed (a topic may hold hundreds of concepts): these are the ones opened.
  const openedTopics = useCollapsed(`learnable.tree-opened.${courseId}`);
  const [find, setFind] = useState("");
  const outline = useQuery({ queryKey: outlineKey(courseId), queryFn: () => courses.outline(courseId) });
  const readOnly = Boolean(course.data?.marketplace_listing_id);
  const { t } = useI18n();
  const { studyStateLabel } = useLabels();

  return (
    <ReadOnlyCourseProvider value={readOnly}>
    <div className="course-workspace">
      <nav className="tree" aria-label={t("course.curriculum")}>
        <NavLink end to={`/courses/${courseId}`} className="tree-course">
          {course.data?.title ?? t("course.fallback")}
        </NavLink>
        <input
          type="search"
          className="tree-find"
          value={find}
          placeholder={t("tree.find")}
          aria-label={t("tree.find")}
          onChange={(e) => setFind(e.target.value)}
        />
        <QueryState query={outline} label={t("course.loadingCurriculum")}>
          {(chapters) => {
            // The branch holding the page you're on stays open, even if you collapsed it.
            const openChapter = chapters.find(
              (c) => c.id === chapterId || c.topics.some((t) => t.id === topicId || t.concepts.some((k) => k.id === conceptId)),
            );
            const openTopic = openChapter?.topics.find((t) => t.id === topicId || t.concepts.some((k) => k.id === conceptId));
            const needle = find.trim().toLocaleLowerCase();
            const hit = (text: string) => !needle || text.toLocaleLowerCase().includes(needle);
            // Searching: every branch with a match is open and the rest is left out.
            const expanded = (id: string, open: boolean) => Boolean(needle) || open || !tree.isCollapsed(id);
            const topicExpanded = (id: string, open: boolean) => Boolean(needle) || open || openedTopics.isCollapsed(id);
            const shownChapters = chapters
              .map((chapter) => {
                if (!needle || hit(chapter.title)) return chapter;
                const topics = chapter.topics
                  .map((topic) => (hit(topic.title) ? topic : { ...topic, concepts: topic.concepts.filter((k) => hit(k.title)) }))
                  .filter((topic) => hit(topic.title) || topic.concepts.length > 0);
                return { ...chapter, topics };
              })
              .filter((chapter) => !needle || hit(chapter.title) || chapter.topics.length > 0);
            return (
              <ul>
                {shownChapters.length === 0 && <li className="hint">{t("tree.noMatch")}</li>}
                {shownChapters.map((chapter) => {
                  const chapterOpen = expanded(chapter.id, chapter.id === openChapter?.id && chapter.id !== chapterId);
                  return (
                    <li key={chapter.id}>
                      <div className="tree-row">
                        {chapter.topics.length > 0 ? (
                          <CollapseToggle
                            expanded={chapterOpen}
                            onToggle={() => tree.toggle(chapter.id)}
                            label={chapter.title}
                            controls={`tree-${chapter.id}`}
                          />
                        ) : (
                          <span className="collapse-spacer" />
                        )}
                        <NavLink to={`/courses/${courseId}/chapters/${chapter.id}`} className="tree-chapter">
                          {chapter.title}
                        </NavLink>
                      </div>
                      {chapter.topics.length > 0 && (
                        <ul id={`tree-${chapter.id}`} hidden={!chapterOpen}>
                          {chapter.topics.map((topic) => {
                            const topicOpen = topicExpanded(topic.id, topic.id === openTopic?.id);
                            return (
                              <li key={topic.id}>
                                <div className="tree-row">
                                  {topic.concepts.length > 0 ? (
                                    <CollapseToggle
                                      expanded={topicOpen}
                                      onToggle={() => openedTopics.toggle(topic.id)}
                                      label={topic.title}
                                      controls={`tree-${topic.id}`}
                                    />
                                  ) : (
                                    <span className="collapse-spacer" />
                                  )}
                                  <NavLink to={`/courses/${courseId}/topics/${topic.id}`} className="tree-topic">
                                    {topic.title}
                                  </NavLink>
                                  {topic.concepts.length > 0 && <span className="tree-count">{topic.concepts.length}</span>}
                                </div>
                                {topic.concepts.length > 0 && (
                                  <ul id={`tree-${topic.id}`} hidden={!topicOpen}>
                                    {topic.concepts.map((concept) => (
                                      <li key={concept.id}>
                                        <NavLink
                                          to={`/courses/${courseId}/concepts/${concept.id}`}
                                          className={`tree-concept state-${concept.study_state.toLowerCase()}`}
                                          title={studyStateLabel[concept.study_state]}
                                        >
                                          {concept.title}
                                        </NavLink>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            );
          }}
        </QueryState>
        {!readOnly && (
          <NavLink to={`/courses/${courseId}/material`} className="tree-extra">
            {t("course.allMaterial")}
          </NavLink>
        )}
        <NavLink to={`/courses/${courseId}/questions`} className="tree-extra">
          {t("course.manageQuestions")}
        </NavLink>
        <NavLink to={`/courses/${courseId}/leaderboard`} className="tree-extra">
          {t("course.leaderboardLink")}
        </NavLink>
        <NavLink to={`/courses/${courseId}/weak-spots`} className="tree-extra">
          {t("course.weakSpots")}
        </NavLink>
      </nav>
      <div className="workspace-main">
        <Outlet />
      </div>
    </div>
    </ReadOnlyCourseProvider>
  );
}
