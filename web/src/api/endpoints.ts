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
  /** Everything held about the account, as one JSON document. */
  exportData: () => call(api.GET("/api/v1/auth/export")),
  /** Deletes the signed-in account and everything it owns. */
  deleteAccount: (password: string) => call(api.POST("/api/v1/auth/delete-account", { body: { password } })),
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
  /** The day of the exam ("2027-01-20"), or null to remove it. */
  setExamDate: (courseId: Id, date: string | null) =>
    call(api.PUT("/api/v1/courses/{course_id}/exam-date", { params: { path: { course_id: courseId } }, body: { date } })),
  update: (courseId: Id, body: Schemas["CourseUpdate"]) =>
    call(api.PATCH("/api/v1/courses/{course_id}", { params: { path: { course_id: courseId } }, body })),
  setPaused: (courseId: Id, paused: boolean) =>
    call(api.POST(paused ? "/api/v1/courses/{course_id}/pause" : "/api/v1/courses/{course_id}/resume", { params: { path: { course_id: courseId } } })),
  setArchived: (courseId: Id, archived: boolean) =>
    call(api.POST(archived ? "/api/v1/courses/{course_id}/archive" : "/api/v1/courses/{course_id}/unarchive", { params: { path: { course_id: courseId } } })),
  remove: (courseId: Id) => call(api.DELETE("/api/v1/courses/{course_id}", { params: { path: { course_id: courseId } } })),
  updateChapter: (chapterId: Id, body: Schemas["ChapterUpdate"]) =>
    call(api.PATCH("/api/v1/chapters/{chapter_id}", { params: { path: { chapter_id: chapterId } }, body })),
  updateTopic: (topicId: Id, body: Schemas["TopicUpdate"]) =>
    call(api.PATCH("/api/v1/topics/{topic_id}", { params: { path: { topic_id: topicId } }, body })),
  /** Deletes chapters, topics, concepts and questions together; all or nothing. */
  deleteCurriculum: (courseId: Id, body: Schemas["CurriculumDelete"]) =>
    call(api.POST("/api/v1/courses/{course_id}/curriculum/bulk-delete", { params: { path: { course_id: courseId } }, body })),
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
  /** Makes the question a drawing question: this image is its answer. */
  setReferenceDrawing: (itemId: Id, file: Blob) => {
    const form = new FormData();
    form.append("file", file, "reference.png");
    return rawRequest<Schemas["LearningItemRead"]>(`/api/v1/learning-items/${itemId}/reference-drawing`, {
      method: "PUT",
      body: form,
    });
  },
  removeReferenceDrawing: (itemId: Id) =>
    call(api.DELETE("/api/v1/learning-items/{item_id}/reference-drawing", { params: { path: { item_id: itemId } } })),
  referenceDrawing: (itemId: Id) => downloadBlob(`/api/v1/learning-items/${itemId}/reference-drawing`),
  answerDrawing: (answerId: Id) => downloadBlob(`/api/v1/answers/${answerId}/drawing`),
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
  answer: (sessionId: Id, questionId: Id, text: string, method: Schemas["AnswerMethod"] = "TEXT", drawing?: string) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/answers", {
        params: { path: { session_id: sessionId } },
        body: { question_formulation_id: questionId, text, method, ...(drawing ? { drawing } : {}) },
      }),
    ),
  /** The questions still to come in this session, the one on screen first. */
  queue: (sessionId: Id) =>
    call(api.GET("/api/v1/review-sessions/{session_id}/queue", { params: { path: { session_id: sessionId } } })),
  /** Makes a question still to come the next one. */
  pick: (sessionId: Id, learningItemId: Id) =>
    call(
      api.POST("/api/v1/review-sessions/{session_id}/pick", {
        params: { path: { session_id: sessionId } },
        body: { learning_item_id: learningItemId },
      }),
    ),
  /** Every question due now in a course, in the order they were added. */
  dueQueue: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}/review-queue", { params: { path: { course_id: courseId } } })),
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
  /** After reviewing the reference: repeat a mostly green answer, which then counts as correct. */
  repeat: (answerId: Id, text: string) =>
    call(api.POST("/api/v1/answers/{answer_id}/repeat", { params: { path: { answer_id: answerId } }, body: { text } })),
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

export type ListingFilters = {
  q?: string;
  category?: Schemas["Category"];
  language?: string;
  size?: "small" | "medium" | "large";
  level?: Schemas["Level"];
  price?: "free" | "paid";
  sort?: Schemas["ListingSort"];
};

export const marketplace = {
  browse: (filters: ListingFilters) =>
    call(api.GET("/api/v1/marketplace/listings", { params: { query: { ...filters, q: filters.q || undefined } } })),
  get: (listingId: Id) =>
    call(api.GET("/api/v1/marketplace/listings/{listing_id}", { params: { path: { listing_id: listingId } } })),
  acquire: (listingId: Id) =>
    call(api.POST("/api/v1/marketplace/listings/{listing_id}/acquire", { params: { path: { listing_id: listingId } } })),
  mine: () => call(api.GET("/api/v1/marketplace/mine")),
  unpublish: (listingId: Id) =>
    call(api.POST("/api/v1/marketplace/listings/{listing_id}/unpublish", { params: { path: { listing_id: listingId } } })),
  forCourse: (courseId: Id) =>
    call(api.GET("/api/v1/courses/{course_id}/marketplace", { params: { path: { course_id: courseId } } })),
  saveInfo: (courseId: Id, body: Schemas["ListingInfo"]) =>
    call(api.PUT("/api/v1/courses/{course_id}/marketplace/info", { params: { path: { course_id: courseId } }, body })),
  publish: (courseId: Id, body: Schemas["ListingPublish"]) =>
    call(
      api.POST("/api/v1/courses/{course_id}/marketplace/publish", { params: { path: { course_id: courseId } }, body }),
    ),
  announce: (courseId: Id, message: string) =>
    call(
      api.POST("/api/v1/courses/{course_id}/marketplace/announce", { params: { path: { course_id: courseId } }, body: { message } }),
    ),
  reviews: (listingId: Id) =>
    call(api.GET("/api/v1/marketplace/listings/{listing_id}/reviews", { params: { path: { listing_id: listingId } } })),
  writeReview: (listingId: Id, body: Schemas["ReviewWrite"]) =>
    call(api.PUT("/api/v1/marketplace/listings/{listing_id}/review", { params: { path: { listing_id: listingId } }, body })),
  deleteReview: (listingId: Id) =>
    call(api.DELETE("/api/v1/marketplace/listings/{listing_id}/review", { params: { path: { listing_id: listingId } } })),
  replyToReview: (reviewId: Id, reply: string) =>
    call(api.PUT("/api/v1/marketplace/reviews/{review_id}/reply", { params: { path: { review_id: reviewId } }, body: { reply } })),
};

export type Period = Schemas["Period"];
export type Scope = Schemas["Scope"];

export const community = {
  leaderboard: (period: Period, scope: Scope) =>
    call(api.GET("/api/v1/community/leaderboard", { params: { query: { period, scope } } })),
  courseLeaderboard: (courseId: Id, period: Period, scope: Scope) =>
    call(api.GET("/api/v1/courses/{course_id}/leaderboard", { params: { path: { course_id: courseId }, query: { period, scope } } })),
  people: (q: string) => call(api.GET("/api/v1/community/people", { params: { query: { q } } })),
  friends: () => call(api.GET("/api/v1/community/friends")),
  requests: () => call(api.GET("/api/v1/community/friend-requests")),
  blocked: () => call(api.GET("/api/v1/community/blocked")),
  profile: (userId: Id) => call(api.GET("/api/v1/community/users/{user_id}", { params: { path: { user_id: userId } } })),
  /** Ask to be friends, or accept their request. */
  befriend: (userId: Id) => call(api.PUT("/api/v1/community/users/{user_id}/friend", { params: { path: { user_id: userId } } })),
  /** Cancel a request you sent, decline one you received, or remove a friend. */
  unfriend: (userId: Id) => call(api.DELETE("/api/v1/community/users/{user_id}/friend", { params: { path: { user_id: userId } } })),
  block: (userId: Id) => call(api.PUT("/api/v1/community/users/{user_id}/block", { params: { path: { user_id: userId } } })),
  unblock: (userId: Id) => call(api.DELETE("/api/v1/community/users/{user_id}/block", { params: { path: { user_id: userId } } })),
};

export const chat = {
  list: () => call(api.GET("/api/v1/chats")),
  thread: (userId: Id, before?: Id) =>
    call(api.GET("/api/v1/chats/{user_id}", { params: { path: { user_id: userId }, query: { before } } })),
  send: (userId: Id, body: string) =>
    call(api.POST("/api/v1/chats/{user_id}", { params: { path: { user_id: userId } }, body: { body } })),
};

export const notifications = {
  inbox: () => call(api.GET("/api/v1/inbox")),
  list: () => call(api.GET("/api/v1/notifications")),
  markRead: (ids?: Id[]) => call(api.POST("/api/v1/notifications/read", { body: { ids } })),
};

/** Push notifications: the daily review reminder. */
export const push = {
  status: () => call(api.GET("/api/v1/push")),
  subscribe: (body: Schemas["PushSubscribe"]) => call(api.POST("/api/v1/push/subscribe", { body })),
  unsubscribe: (endpoint: string) => call(api.POST("/api/v1/push/unsubscribe", { body: { endpoint } })),
  reminder: (hour: number | null) => call(api.PUT("/api/v1/push/reminder", { body: { hour } })),
  test: () => call(api.POST("/api/v1/push/test")),
};

/** Tags to hear about: a notification when a course carrying one is first published. */
export const interests = {
  get: () => call(api.GET("/api/v1/interests")),
  follow: (tag: string) => call(api.PUT("/api/v1/interests", { body: { tag } })),
  unfollow: (tag: string) => call(api.DELETE("/api/v1/interests", { params: { query: { tag } } })),
};

export type ReportKind = Schemas["ReportKind"];

/** Tell the administrator about a person, a message you received or a review. */
export const reports = {
  send: (kind: ReportKind, targetId: Id, reason: string) =>
    call(api.POST("/api/v1/reports", { body: { kind, target_id: targetId, reason } })),
};

export const payments = {
  payout: () => call(api.GET("/api/v1/payments/payout")),
  onboarding: () => call(api.POST("/api/v1/payments/payout/onboarding")),
  checkout: (listingId: Id, code = "") =>
    call(api.POST("/api/v1/marketplace/listings/{listing_id}/checkout", { params: { path: { listing_id: listingId } }, body: { code } })),
  /** What a discount code makes the price. */
  quote: (listingId: Id, code: string) =>
    call(api.GET("/api/v1/marketplace/listings/{listing_id}/discount", { params: { path: { listing_id: listingId }, query: { code } } })),
  discounts: (courseId: Id) => call(api.GET("/api/v1/courses/{course_id}/marketplace/discounts", { params: { path: { course_id: courseId } } })),
  createDiscount: (courseId: Id, body: Schemas["DiscountCreate"]) =>
    call(api.POST("/api/v1/courses/{course_id}/marketplace/discounts", { params: { path: { course_id: courseId } }, body })),
  deleteDiscount: (courseId: Id, discountId: Id) =>
    call(api.DELETE("/api/v1/courses/{course_id}/marketplace/discounts/{discount_id}", { params: { path: { course_id: courseId, discount_id: discountId } } })),
  refund: (orderId: Id) => call(api.POST("/api/v1/marketplace/orders/{order_id}/refund", { params: { path: { order_id: orderId } } })),
  order: (orderId: Id) => call(api.GET("/api/v1/marketplace/orders/{order_id}", { params: { path: { order_id: orderId } } })),
  sales: () => call(api.GET("/api/v1/marketplace/sales")),
};

export const admin = {
  summary: () => call(api.GET("/api/v1/admin/summary")),
  users: () => call(api.GET("/api/v1/admin/users")),
  updateUser: (id: Id, body: Schemas["AdminUserUpdate"]) =>
    call(api.PATCH("/api/v1/admin/users/{user_id}", { params: { path: { user_id: id } }, body })),
  deleteUser: (id: Id) =>
    call(api.DELETE("/api/v1/admin/users/{user_id}", { params: { path: { user_id: id } } })),
  resetPassword: (id: Id) =>
    call(api.POST("/api/v1/admin/users/{user_id}/password", { params: { path: { user_id: id } } })),
  invitations: () => call(api.GET("/api/v1/admin/invitations")),
  createInvitation: (body: Schemas["InvitationCreate"]) => call(api.POST("/api/v1/admin/invitations", { body })),
  revokeInvitation: (id: Id) =>
    call(api.DELETE("/api/v1/admin/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })),
  deleteReview: (id: Id) => call(api.DELETE("/api/v1/admin/reviews/{review_id}", { params: { path: { review_id: id } } })),
  reports: () => call(api.GET("/api/v1/admin/reports")),
  resolveReport: (id: Id) => call(api.POST("/api/v1/admin/reports/{report_id}/resolve", { params: { path: { report_id: id } } })),
  reopenReport: (id: Id) => call(api.POST("/api/v1/admin/reports/{report_id}/reopen", { params: { path: { report_id: id } } })),
};
