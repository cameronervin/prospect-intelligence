import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));
vi.mock("@/server/env", () => ({ backendBaseUrl: () => "http://backend.internal:8000" }));

import { backendAuth } from "./auth-session";

describe("backendAuth", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends credentials in a JSON body to a query-free URL without following redirects", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({}));
    vi.stubGlobal("fetch", fetcher);

    await backendAuth("token", undefined, {
      method: "POST",
      body: JSON.stringify({ email: "alex.morgan@example.test", password: "private-value" }),
    });

    const [requestUrl, init] = fetcher.mock.calls[0] ?? [];
    const url = new URL(String(requestUrl));
    expect(url.href).toBe("http://backend.internal:8000/api/v1/auth/token");
    expect(url.search).toBe("");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({ email: "alex.morgan@example.test", password: "private-value" }),
    );
    expect(init?.cache).toBe("no-store");
    expect(init?.redirect).toBe("manual");
  });
});
