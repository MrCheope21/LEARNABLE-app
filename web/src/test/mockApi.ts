import { vi } from "vitest";

export interface Recorded {
  method: string;
  path: string;
  body: unknown;
  headers: Headers;
}

type Responder = (request: Recorded, call: number) => { status?: number; body?: unknown } | undefined;

/**
 * A scripted backend: routes are [METHOD, path pattern, responder]. Unmatched requests fail the
 * test loudly instead of hanging. Every request is recorded for assertions.
 */
export function mockApi(routes: [string, RegExp, Responder][]) {
  const requests: Recorded[] = [];
  const calls = new Map<number, number>();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    let body: unknown = undefined;
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) body = await request.clone().json();
    const recorded: Recorded = { method: request.method, path: url.pathname, body, headers: request.headers };
    requests.push(recorded);
    const index = routes.findIndex(([method, pattern]) => method === request.method && pattern.test(url.pathname));
    if (index < 0) throw new Error(`Unexpected request ${request.method} ${url.pathname}`);
    const count = (calls.get(index) ?? 0) + 1;
    calls.set(index, count);
    const route = routes[index];
    const result = route ? route[2](recorded, count) : undefined;
    const status = result?.status ?? 200;
    if (status === 204) return new Response(null, { status });
    return new Response(JSON.stringify(result?.body ?? {}), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { requests, fetchMock };
}

export const ok = (body: unknown) => () => ({ body });
export const sequence =
  (...bodies: unknown[]) =>
  (_request: Recorded, call: number) => ({ body: bodies[Math.min(call, bodies.length) - 1] });
export const failWith = (status: number, errorType: string, message = "x") => () => ({
  status,
  body: { error_type: errorType, message, details: {} },
});
