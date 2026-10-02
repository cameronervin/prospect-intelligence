import { afterEach, describe, expect, it, vi } from "vitest";

const { currentSession } = vi.hoisted(() => ({ currentSession: vi.fn() }));
vi.mock("@/server/auth-session", () => ({
  SESSION_COOKIE: "prospect_session",
  authResponseHeaders: {
    "Cache-Control": "no-store, max-age=0",
    Pragma: "no-cache",
  },
  currentSession,
}));

import { GET } from "./route";

describe("session BFF", () => {
  afterEach(() => currentSession.mockReset());

  it("returns authenticated sessions with explicit anti-cache headers", async () => {
    currentSession.mockResolvedValue({ subject: "usr_alex_morgan" });

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0");
    expect(response.headers.get("pragma")).toBe("no-cache");
  });

  it("clears rejected sessions without making the response cacheable", async () => {
    currentSession.mockResolvedValue(undefined);

    const response = await GET();

    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0");
    expect(response.headers.get("pragma")).toBe("no-cache");
    expect(response.headers.get("set-cookie")).toContain("prospect_session=");
  });
});
