import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

/** Every API model, generated from the backend's OpenAPI schema (npm run gen:api). */
export type Schemas = components["schemas"];

/** Unset means "same origin" (the dev server proxies /api to the backend). */
export const API_BASE_URL = import.meta.env.LEARNABLE_PUBLIC_API_BASE_URL || window.location.origin;

const TOKEN_KEY = "learnable.accessToken";
export const SESSION_EXPIRED_EVENT = "learnable:session-expired";

/**
 * The backend access token. It lives in localStorage so a reload keeps you signed in; it grants
 * access to this user's study data only, never to AI providers (those keys stay on the server).
 */
export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Storage unavailable: nothing to clear.
    }
  },
};

/** A failed API call, keeping the backend's error envelope (docs/API.md "Errors"). */
export class ApiError extends Error {
  readonly status: number;
  readonly errorType: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, errorType: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorType = errorType;
    this.details = details;
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = tokenStore.get();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};

// fetch is looked up per call (not captured once), so it can be instrumented or replaced.
export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: (request) => globalThis.fetch(request) });
api.use(auth);

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Awaits an openapi-fetch call and returns its data, or throws an ApiError. */
export async function call<T>(request: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await request;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "transport", "Can't reach the server.");
  }
  return handle(result.response, result.data, result.error);
}

/** For requests openapi-fetch can't express well (multipart uploads). */
export async function rawRequest<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "transport", "Can't reach the server.");
  }
  const body: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  return handle(response, body as T, body);
}

/** A file download that needs the access token (so no plain link): returns the bytes. */
export async function downloadBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers });
  } catch {
    throw new ApiError(0, "transport", "Can't reach the server.");
  }
  if (response.ok) return response.blob();
  const body: unknown = await response.json().catch(() => undefined);
  return handle<Blob>(response, undefined, body);
}

function handle<T>(response: Response, data: T | undefined, error: unknown): T {
  if (response.ok) return data as T;
  const envelope = (error ?? {}) as { error_type?: unknown; message?: unknown; details?: unknown };
  const errorType = typeof envelope.error_type === "string" ? envelope.error_type : "http_error";
  const message = typeof envelope.message === "string" ? envelope.message : response.statusText;
  const details =
    envelope.details && typeof envelope.details === "object"
      ? (envelope.details as Record<string, unknown>)
      : {};
  if (response.status === 401) {
    tokenStore.clear();
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
  throw new ApiError(response.status, errorType, message, details);
}

/** Text safe to show a user: our own wording for known errors, never a raw payload. */
export function userMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  switch (error.errorType) {
    case "transport":
      return "Can't reach the server. Check your connection and try again.";
    case "authentication_failed":
      return error.message || "Your session has expired. Please sign in again.";
    case "validation_error":
      // Rejections with a reason (e.g. wrong_password) carry a message written for the user.
      return typeof error.details.reason === "string" && error.message
        ? error.message
        : "Some of the information entered isn't valid.";
    case "not_found":
      return "This item no longer exists.";
    // The server's own message names its actual limit / the formats accepted for this upload.
    case "payload_too_large":
      return error.message || "This file is too large.";
    case "unsupported_media_type":
      return error.message || "This file type isn't supported. Use PDF, Word, PowerPoint, text or Markdown files.";
    case "ai_not_configured":
      return "The AI isn't set up on the server yet.";
    case "ai_unavailable":
      return "The AI is temporarily unavailable. Please try again later.";
    case "ai_invalid_output":
      return "The AI gave an unusable response. Please try again.";
    case "invalid_state_transition":
      return "That action isn't possible in the current state.";
    case "internal_error":
      return "Something went wrong on the server. Please try again.";
    default:
      return error.message || "Something went wrong. Please try again.";
  }
}
