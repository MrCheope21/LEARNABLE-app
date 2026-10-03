// Every backend call the web client makes, typed by the generated OpenAPI schema. Components
// never build URLs; they call these. Learning logic (outcomes, levels, due dates, mastery) stays
// on the server: nothing here computes it.
import { ApiError, api, call, downloadBlob, rawRequest, type Schemas } from "./client";

type Id = string;

const LARGE_UPLOAD_BYTES = 20 * 1024 * 1024;

/** Minutes east of UTC, so "today" and "tomorrow" in review load are the user's own days. */
export function utcOffsetMinutes(): number {
  return -new Date().getTimezoneOffset();
}

/** The device's IANA timezone ("Europe/Rome"), or null if the browser doesn't say. */
export function deviceTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

export const auth = {
  login: (body: Schemas["UserLogin"]) => call(api.POST("/api/v1/auth/login", { body })),
  register: (body: Schemas["UserCreate"]) => call(api.POST("/api/v1/auth/register", { body })),
  me: () => call(api.GET("/api/v1/auth/me")),
  updateMe: (body: Schemas["UserPreferencesUpdate"]) => call(api.PATCH("/api/v1/auth/me", { body })),
  requestPasswordReset: (email: string) =>
    call(api.POST("/api/v1/auth/password-reset/request", { body: { email } })),
  confirmPasswordReset: (token: string, newPassword: string) =>
    call(api.POST("/api/v1/auth/password-reset/confirm", { body: { token, new_password: newPassword } })),
  changePassword: (currentPassword: string, newPassword: string) =>
    call(
      api.POST("/api/v1/auth/change-password", {
        body: { current_password: currentPassword, new_password: newPassword },
      }),
    ),
};

export const dashboard = {
  get: () => call(api.GET("/api/v1/dashboard")),
  activity: (weeks: number) => call(api.GET("/api/v1/activity", { params: { query: { weeks } } })),
  courseSummary: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}/summary", { params: { path: { course_id: courseId } } })),
  weakSpots: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}/weak-spots", { params: { path: { course_id: courseId } } })),
};

export const courses = {
  list: () => call(api.GET("/api/v1/courses")),
  get: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}", { params: { path: { course_id: courseId } } })),
  create: (body: Schemas["CourseCreate"]) => call(api.POST("/api/v1/courses", { body })),
  update: (courseId: Id, body: Schemas["CourseUpdate"]) =>
    call(api.PATCH("/api/v1/courses/{course_id}", { params: { path: { course_id: courseId } }, body })),
  updateChapter: (chapterId: Id, body: Schemas["ChapterUpdate"]) =>
    call(api.PATCH("/api/v1/chapters/{chapter_id}", { params: { path: { chapter_id: chapterId } }, body })),
  updateTopic: (topicId: Id, body: Schemas["TopicUpdate"]) =>
    call(api.PATCH("/api/v1/topics/{topic_id}", { params: { path: { topic_id: topicId } }, body })),
  outline: (courseId: Id) =>
    call(
      api.GET("/api/v1/courses/{course_id}/outline", { params: { path: { course_id: courseId } } }),
    ),
  /** `order` places it; pass the current chapter count to append it at the end. */
  createChapter: (courseId: Id, title: string, order: number) =>
    call(
      api.POST("/api/v1/courses/{course_id}/chapters", {
        params: { path: { course_id: courseId } },
        body: { title, description: "", order },
      }),
    ),
};

/** Drag and drop: a parent's children in their new order, each exactly once (else 422). */
export const reorder = {
  chapters: (courseId: Id, ids: Id[]) =>
    call(api.PUT("/api/v1/courses/{course_id}/chapter-order", { params: { path: { course_id: courseId } }, body: { ids } })),
  topics: (chapterId: Id, ids: Id[]) =>
    call(api.PUT("/api/v1/chapters/{chapter_id}/topic-order", { params: { path: { chapter_id: chapterId } }, body: { ids } })),
  concepts: (topicId: Id, ids: Id[]) =>
    call(api.PUT("/api/v1/topics/{topic_id}/concept-order", { params: { path: { topic_id: topicId } }, body: { ids } })),
  learningItems: (conceptId: Id, ids: Id[]) =>
    call(
      api.PUT("/api/v1/concepts/{concept_id}/learning-item-order", { params: { path: { concept_id: conceptId } }, body: { ids } }),
    ),
};

export type ConceptAction = "activate" | "mark-studied" | "pause" | "resume" | "deactivate" | "complete";

export const concepts = {
  get: (conceptId: Id) =>
    call(api.GET("/api/v1/concepts/{concept_id}", { params: { path: { concept_id: conceptId } } })),
  update: (conceptId: Id, body: Schemas["ConceptUpdate"]) =>
    call(api.PATCH("/api/v1/concepts/{concept_id}", { params: { path: { concept_id: conceptId } }, body })),
  perform: (conceptId: Id, action: ConceptAction) => {
    const params = { params: { path: { concept_id: conceptId } } };
    switch (action) {
      case "activate":
        return call(api.POST("/api/v1/concepts/{concept_id}/activate", params));
      case "mark-studied":
        return call(api.POST("/api/v1/concepts/{concept_id}/mark-studied", params));
      case "pause":
        return call(api.POST("/api/v1/concepts/{concept_id}/pause", params));
      case "resume":
        return call(api.POST("/api/v1/concepts/{concept_id}/resume", params));
      case "deactivate":
        return call(api.POST("/api/v1/concepts/{concept_id}/deactivate", params));
      case "complete":
        return call(api.POST("/api/v1/concepts/{concept_id}/complete", params));
    }
  },
  learningItems: (conceptId: Id) =>
    call(
      api.GET("/api/v1/concepts/{concept_id}/learning-items", {
        params: { path: { concept_id: conceptId } },
      }),
    ),
  consolidationPlan: (conceptId: Id) =>
    call(
      api.GET("/api/v1/concepts/{concept_id}/consolidation", {
        params: { path: { concept_id: conceptId } },
      }),
    ),
  /** "I have studied this concept": resumes the unfinished batch or starts the next one. */
  startConsolidation: (conceptId: Id) =>
    call(
      api.POST("/api/v1/concepts/{concept_id}/consolidation", {
        params: { path: { concept_id: conceptId } },
      }),
    ),
  generateItems: (conceptId: Id) =>
    call(
      api.POST("/api/v1/concepts/{concept_id}/learning-items/generate", {
        params: { path: { concept_id: conceptId } },
      }),
    ),
};

export const learningItems = {
  setInTraining: (itemId: Id, inTraining: boolean) => {
    const params = { params: { path: { item_id: itemId } } };
    return inTraining
      ? call(api.POST("/api/v1/learning-items/{item_id}/train", params))
      : call(api.POST("/api/v1/learning-items/{item_id}/untrain", params));
  },
  sources: (itemId: Id) =>
    call(
      api.GET("/api/v1/learning-items/{item_id}/sources", { params: { path: { item_id: itemId } } }),
    ),
  /** Every item of a Course with its questions, in course order (the question manager). */
  listForCourse: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}/learning-items", { params: { path: { course_id: courseId } } })),
  bulk: (courseId: Id, body: Schemas["BulkItemAction"]) =>
    call(api.POST("/api/v1/courses/{course_id}/learning-items/bulk", { params: { path: { course_id: courseId } }, body })),
  update: (itemId: Id, body: Schemas["LearningItemUpdate"]) =>
    call(api.PATCH("/api/v1/learning-items/{item_id}", { params: { path: { item_id: itemId } }, body })),
  addQuestion: (itemId: Id, text: string, questionType: Schemas["QuestionType"] = "RECALL") =>
    call(
      api.POST("/api/v1/learning-items/{item_id}/questions", {
        params: { path: { item_id: itemId } },
        body: { question_type: questionType, text },
      }),
    ),
  updateQuestion: (questionId: Id, text: string) =>
    call(api.PATCH("/api/v1/questions/{question_id}", { params: { path: { question_id: questionId } }, body: { text } })),
  deleteQuestion: (questionId: Id) =>
    call(api.DELETE("/api/v1/questions/{question_id}", { params: { path: { question_id: questionId } } })),
};

export const curriculum = {
  generate: (courseId: Id, chapterId: Id | null) =>
    call(
      api.POST("/api/v1/courses/{course_id}/curriculum-proposals", {
        params: { path: { course_id: courseId } },
        body: { chapter_id: chapterId },
      }),
    ),
  get: (proposalId: Id) =>
    call(
      api.GET("/api/v1/curriculum-proposals/{proposal_id}", {
        params: { path: { proposal_id: proposalId } },
      }),
    ),
  apply: (proposalId: Id, body: Schemas["CurriculumApply"]) =>
    call(
      api.POST("/api/v1/curriculum-proposals/{proposal_id}/apply", {
        params: { path: { proposal_id: proposalId } },
        body,
      }),
    ),
  reject: (proposalId: Id) =>
    call(
      api.DELETE("/api/v1/curriculum-proposals/{proposal_id}", {
        params: { path: { proposal_id: proposalId } },
      }),
    ),
};

export const documents = {
  list: (courseId: Id, chapterId?: Id) =>
    call(
      api.GET("/api/v1/courses/{course_id}/documents", {
        params: { path: { course_id: courseId }, query: chapterId ? { chapter_id: chapterId } : {} },
      }),
    ),
  upload: (courseId: Id, file: File, chapterId?: Id, purpose: Schemas["DocumentPurpose"] = "MATERIAL") => {
    const form = new FormData();
    form.append("file", file);
    if (chapterId) form.append("chapter_id", chapterId);
    form.append("purpose", purpose);
    return rawRequest<Schemas["DocumentRead"]>(`/api/v1/courses/${courseId}/documents`, {
      method: "POST",
      body: form,
    }).catch((error: unknown) => {
      // The server refuses an oversized body before reading it, which proxies and browsers can
      // report as a dropped connection rather than a 413. For a large file, say what likely
      // happened instead of "can't reach the server".
      if (error instanceof ApiError && error.errorType === "transport" && file.size > LARGE_UPLOAD_BYTES) {
        const mb = Math.round(file.size / (1024 * 1024));
        throw new ApiError(
          413,
          "payload_too_large",
          `Couldn't upload this ${mb} MB file. It's probably over the server's size limit: try a smaller file, or split it.`,
        );
      }
      throw error;
    });
  },
  remove: (documentId: Id) =>
    call(
      api.DELETE("/api/v1/documents/{document_id}", {
        params: { path: { document_id: documentId } },
      }),
    ),
  /** The original file, fetched with the access token (the server checks ownership). */
  download: (documentId: Id) => downloadBlob(`/api/v1/documents/${documentId}/file`),
  passage: (documentId: Id, chunkId: Id) =>
    call(
      api.GET("/api/v1/documents/{document_id}/chunks/{chunk_id}", {
        params: { path: { document_id: documentId, chunk_id: chunkId } },
      }),
    ),
};

export const study = {
  start: (courseId: Id, body: Schemas["SessionCreate"]) =>
    call(
      api.POST("/api/v1/courses/{course_id}/review-sessions", {
        params: { path: { course_id: courseId } },
        body,
      }),
    ),
  get: (sessionId: Id) =>
    call(
      api.GET("/api/v1/review-sessions/{session_id}", {
        params: { path: { session_id: sessionId } },
      }),
    ),
  hint: (sessionId: Id) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/hint", {
        params: { path: { session_id: sessionId } },
      }),
    ),
  next: (sessionId: Id) =>
    call(
      api.GET("/api/v1/review-sessions/{session_id}/next", {
        params: { path: { session_id: sessionId } },
      }),
    ),
  answer: (sessionId: Id, questionId: Id, text: string) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/answers", {
        params: { path: { session_id: sessionId } },
        body: { question_formulation_id: questionId, text, method: "TEXT" },
      }),
    ),
  skip: (sessionId: Id) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/skip", {
        params: { path: { session_id: sessionId } },
      }),
    ),
  end: (sessionId: Id) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/end", {
        params: { path: { session_id: sessionId } },
      }),
    ),
  getAnswer: (answerId: Id) =>
    call(api.GET("/api/v1/answers/{answer_id}", { params: { path: { answer_id: answerId } } })),
  retryEvaluation: (answerId: Id) =>
    call(
      api.POST("/api/v1/answers/{answer_id}/evaluate", {
        params: { path: { answer_id: answerId } },
      }),
    ),
  /** A second opinion: the evaluator sees the student's objection. Changes no grade. */
  dispute: (answerId: Id, argument: string) =>
    call(
      api.POST("/api/v1/answers/{answer_id}/dispute", {
        params: { path: { answer_id: answerId } },
        body: { argument },
      }),
    ),
  override: (answerId: Id, outcome: Schemas["ReviewOutcome"]) =>
    call(
      api.POST("/api/v1/answers/{answer_id}/override", {
        params: { path: { answer_id: answerId } },
        body: { outcome },
      }),
    ),
};

export const progress = {
  home: () =>
    call(api.GET("/api/v1/home", { params: { query: { utc_offset_minutes: utcOffsetMinutes() } } })),
  course: (courseId: Id) =>
    call(
      api.GET("/api/v1/courses/{course_id}/progress", {
        params: { path: { course_id: courseId }, query: { utc_offset_minutes: utcOffsetMinutes() } },
      }),
    ),
};
