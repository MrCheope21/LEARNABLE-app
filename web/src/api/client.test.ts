import { describe, expect, it, vi } from "vitest";
import { failWith, mockApi, ok } from "../test/mockApi";
import { ApiError, SESSION_EXPIRED_EVENT, tokenStore, userMessage } from "./client";
import { courses } from "./endpoints";

describe("API client", () => {
  it("sends the backend token, never anything else", async () => {
    const { requests } = mockApi([["GET", /\/api\/v1\/courses$/, ok([])]]);
    tokenStore.set("abc");

    await courses.list();

    expect(requests[0]?.headers.get("Authorization")).toBe("Bearer abc");
  });

  it("turns the error envelope into an ApiError with a user-safe message", async () => {
    mockApi([["GET", /\/api\/v1\/courses\/[^/]+$/, failWith(404, "not_found", "Course not found")]]);

    const error = await courses.get("00000000-0000-0000-0000-000000000000").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect(userMessage(error)).toBe("This item no longer exists.");
  });

  it("signs out on 401", async () => {
    mockApi([["GET", /\/api\/v1\/courses$/, failWith(401, "authentication_failed", "Invalid token")]]);
    tokenStore.set("expired");
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);

    await expect(courses.list()).rejects.toBeInstanceOf(ApiError);

    expect(tokenStore.get()).toBeNull();
    expect(expired).toHaveBeenCalled();
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it("reports an unreachable server as a transport error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await courses.list().catch((e: unknown) => e);

    expect((error as ApiError).errorType).toBe("transport");
    expect(userMessage(error)).toMatch(/Can't reach the server/);
  });
});
