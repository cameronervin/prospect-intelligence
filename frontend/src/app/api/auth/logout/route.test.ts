import { describe, expect, it, vi } from "vitest";

vi.mock("@/server/auth-session", () => ({
  SESSION_COOKIE: "prospect_session",
  authResponseHeaders: {
    "Cache-Control": "no-store, max-age=0",
    Pragma: "no-cache",
  },
}));

import { POST } from "./route";

describe("logout BFF", () => {
  it("clears the session with explicit anti-cache headers", async () => {
    const response = await POST();

    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0");
    expect(response.headers.get("pragma")).toBe("no-cache");
    expect(response.headers.get("set-cookie")).toContain("prospect_session=");
    expect(response.headers.get("set-cookie")).toContain("Expires=Thu, 01 Jan 1970");
  });
});
