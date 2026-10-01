import { afterEach, describe, expect, it, vi } from "vitest";

const { backendAuth, currentToken } = vi.hoisted(() => ({
  backendAuth: vi.fn(),
  currentToken: vi.fn(),
}));
vi.mock("@/server/auth-session", async () => {
  const { BackendTokenSchema } = await import("@/features/auth/schemas");
  return {
    BackendTokenSchema,
    SESSION_COOKIE: "prospect_session",
    backendAuth,
    currentToken,
    sessionCookieOptions: { httpOnly: true, sameSite: "strict", path: "/", secure: true },
  };
});

import { POST } from "./route";

describe("refresh BFF", () => {
  afterEach(() => {
    backendAuth.mockReset();
    currentToken.mockReset();
  });

  it("preserves the cookie when the backend is temporarily unavailable", async () => {
    currentToken.mockResolvedValue("current-token");
    backendAuth.mockResolvedValue(Response.json({}, { status: 503 }));

    const response = await POST();

    expect(response.status).toBe(503);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("clears the cookie only when the backend rejects the session", async () => {
    currentToken.mockResolvedValue("expired-token");
    backendAuth.mockResolvedValue(Response.json({}, { status: 401 }));

    const response = await POST();

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toContain("prospect_session=");
    expect(response.headers.get("set-cookie")).toContain("Expires=Thu, 01 Jan 1970");
  });
});
