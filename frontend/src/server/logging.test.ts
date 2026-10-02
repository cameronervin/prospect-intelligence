import { afterEach, describe, expect, it, vi } from "vitest";

import { correlationId, serverLog } from "./logging";
import { onRequestError, register } from "../instrumentation";

describe("server logging", () => {
  afterEach(() => vi.restoreAllMocks());

  it("writes one structured record and redacts credential fields", () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);

    serverLog("info", "frontend_test_event", {
      correlation_id: "request-1",
      api_key: "private-value",
      detail: "line one\nline two",
    });

    expect(info).toHaveBeenCalledOnce();
    const record = JSON.parse(String(info.mock.calls[0]?.[0])) as Record<string, unknown>;
    expect(record).toMatchObject({
      event: "frontend_test_event",
      level: "info",
      logger: "frontend.server",
      service: "langchain-takehome-frontend",
      correlation_id: "request-1",
      api_key: "[REDACTED]",
      detail: "line one\nline two",
    });
  });

  it("accepts bounded safe correlation identifiers and replaces unsafe values", () => {
    expect(correlationId("client-request_123")).toBe("client-request_123");
    expect(correlationId("invalid correlation")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("logs startup and server errors without exception messages or raw request paths", () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);

    register();
    onRequestError(
      Object.assign(new Error("private exception detail"), { digest: "safe-digest" }),
      {
        path: "/accounts/private?token=private",
        method: "GET",
        headers: { authorization: "Bearer private" },
      },
      {
        routerKind: "App Router",
        routePath: "/accounts/[id]",
        routeType: "route",
        renderSource: "server-rendering",
        revalidateReason: undefined,
      },
    );

    const startup = JSON.parse(String(info.mock.calls[0]?.[0])) as Record<string, unknown>;
    const failure = JSON.parse(String(error.mock.calls[0]?.[0])) as Record<string, unknown>;
    expect(startup.event).toBe("frontend_started");
    expect(failure).toMatchObject({
      event: "frontend_request_error",
      error_type: "Error",
      error_digest: "safe-digest",
      route: "/accounts/[id]",
    });
    expect(JSON.stringify(failure)).not.toContain("private");
  });
});
