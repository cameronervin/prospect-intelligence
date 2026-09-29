import { afterEach, describe, expect, it, vi } from "vitest";

import { getBackendHealth } from "@/server/backend-health";

describe("getBackendHealth", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("accepts only the ready response contract", async () => {
    vi.stubEnv("BACKEND_BASE_URL", "http://backend.internal:8000");
    const fetcher = vi.fn(async () => Response.json({ status: "ready" }));

    const result = await getBackendHealth(fetcher, 100, () => new Date("2026-09-28T12:00:00Z"));

    expect(result).toEqual({ kind: "ready", checkedAt: "2026-09-28T12:00:00.000Z" });
    expect(fetcher).toHaveBeenCalledWith(
      new URL("http://backend.internal:8000/health/ready"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it.each([
    Response.json({ status: "not_ready" }, { status: 503 }),
    Response.json({ unexpected: true }),
  ])("degrades for failed or malformed responses", async (response) => {
    const result = await getBackendHealth(async () => response);

    expect(result.kind).toBe("degraded");
  });

  it("degrades when the request throws", async () => {
    const result = await getBackendHealth(async () => {
      throw new Error("private transport detail");
    });

    expect(result.kind).toBe("degraded");
  });
});
