import { afterEach, describe, expect, it, vi } from "vitest";

const { backendAuth } = vi.hoisted(() => ({ backendAuth: vi.fn() }));
vi.mock("@/server/auth-session", async () => {
  const { BackendTokenSchema } = await import("@/features/auth/schemas");
  return {
    BackendTokenSchema,
    SESSION_COOKIE: "prospect_session",
    authResponseHeaders: {
      "Cache-Control": "no-store, max-age=0",
      Pragma: "no-cache",
    },
    backendAuth,
    sessionCookieOptions: { httpOnly: true, sameSite: "strict", path: "/", secure: true },
  };
});

import { POST } from "./route";

const payload = {
  access_token: "header.payload.signature",
  token_type: "bearer",
  expires_at: "2026-10-01T13:00:00Z",
  absolute_expires_at: "2026-10-01T20:00:00Z",
  user: {
    subject: "usr_alex_morgan",
    email: "alex.morgan@example.test",
    display_name: "Alex Morgan",
    tenant_id: "tenant-demo",
    rep_id: "alex-morgan",
    roles: ["sales_rep"],
  },
};

describe("login BFF", () => {
  afterEach(() => {
    backendAuth.mockReset();
    vi.restoreAllMocks();
  });

  it("stores the bearer only in a hardened HttpOnly cookie", async () => {
    backendAuth.mockResolvedValue(Response.json(payload));
    const response = await POST(
      new Request("http://localhost/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: "alex.morgan@example.test",
          password: "prospect-demo",
        }),
      }),
    );

    expect(response.status).toBe(200);
    expect(JSON.stringify(await response.json())).not.toContain(payload.access_token);
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("prospect_session=header.payload.signature");
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=strict");
    expect(cookie).toContain("Path=/");
    expect(cookie).toContain("Secure");
    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0");
    expect(response.headers.get("pragma")).toBe("no-cache");
    expect(response.headers.get("location")).toBeNull();
    expect(backendAuth).toHaveBeenCalledWith(
      "token",
      undefined,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "alex.morgan@example.test",
          password: "prospect-demo",
        }),
      }),
    );
  });

  it("maps all backend credential failures to one public error", async () => {
    backendAuth.mockResolvedValue(Response.json({}, { status: 401 }));
    const response = await POST(
      new Request("http://localhost/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: "unknown@example.test", password: "wrong" }),
      }),
    );

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "invalid_credentials" });
    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0");
    expect(response.headers.get("pragma")).toBe("no-cache");
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not log credentials or put them in response headers", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    backendAuth.mockResolvedValue(Response.json({}, { status: 401 }));

    const request = new Request("http://localhost/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "alex.morgan@example.test", password: "private-value" }),
    });
    const response = await POST(request);

    expect(new URL(request.url).search).toBe("");
    expect([...response.headers.values()].join(" ")).not.toContain("private-value");
    expect(log).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });
});
