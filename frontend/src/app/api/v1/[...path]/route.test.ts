import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

function context(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("same-origin API proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("uses only the HttpOnly session cookie for backend identity", async () => {
    vi.stubEnv("BACKEND_BASE_URL", "http://backend.internal:8000");
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [] }));
    vi.stubGlobal("fetch", fetcher);

    const response = await GET(
      new NextRequest("http://localhost/api/v1/accounts", {
        headers: {
          authorization: "Bearer browser-controlled",
          "x-tenant-id": "tenant-other",
          "x-rep-id": "other",
          cookie: "prospect_session=signed-token; secret=1",
        },
      }),
      context(["accounts"]),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://backend.internal:8000/api/v1/accounts");
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe("Bearer signed-token");
    expect(headers.get("x-tenant-id")).toBeNull();
    expect(headers.get("x-rep-id")).toBeNull();
    expect(headers.get("cookie")).toBeNull();
  });

  it("does not expose backend authentication endpoints to browser JavaScript", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);

    const response = await POST(
      new NextRequest("http://localhost/api/v1/auth/token", { method: "POST" }),
      context(["auth", "token"]),
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ error: { code: "not_found" } });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("returns the typed retryable envelope when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("ECONNREFUSED")));

    const response = await POST(
      new NextRequest("http://localhost/api/v1/prospect-runs", {
        method: "POST",
        body: JSON.stringify({ account_id: "acme-foods" }),
      }),
      context(["prospect-runs"]),
    );

    expect(response.status).toBe(503);
    const body: unknown = await response.json();
    expect(body).toEqual({
      error: {
        code: "service_unavailable",
        message: "The prospect service is temporarily unavailable.",
        retryable: true,
        issues: [],
      },
    });
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
  });

  it.each([[["..", "..", "docs"]], [["prospect-runs", "..", "..", "health"]], [["."]]])(
    "rejects dot segments that would escape /api/v1 (%j)",
    async (path) => {
      const fetcher = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetcher);

      const response = await GET(new NextRequest("http://localhost/api/v1/x"), context(path));

      expect(response.status).toBe(400);
      expect(await response.json()).toMatchObject({ error: { code: "validation_error" } });
      expect(fetcher).not.toHaveBeenCalled();
    },
  );

  it("forwards POST bodies and passes the backend status and content type through", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response('{"id":"run-1"}', {
        status: 202,
        headers: { "content-type": "application/json", "set-cookie": "x=1" },
      }),
    );
    vi.stubGlobal("fetch", fetcher);

    const response = await POST(
      new NextRequest("http://localhost/api/v1/prospect-runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ account_id: "acme-foods" }),
      }),
      context(["prospect-runs"]),
    );

    expect(response.status).toBe(202);
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(fetcher.mock.calls[0]?.[1]?.body).toBe('{"account_id":"acme-foods"}');
  });
});
