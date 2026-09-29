import { describe, expect, it, vi } from "vitest";

import { createProspectClient } from "@/lib/prospect-api";

describe("prospect API boundary", () => {
  it("sends the synthetic identity headers when a run is created", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "queued",
        stage: "Preparing research",
        progress_percent: 0,
        source_coverage: [],
      }),
    );
    const client = createProspectClient({ fetcher, tenantId: "demo-carrier", repId: "rep-7" });

    await client.startRun("acct-1");

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/prospect-runs",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-Rep-Id": "rep-7",
          "X-Tenant-Id": "demo-carrier",
        }),
        body: JSON.stringify({ account_id: "acct-1" }),
      }),
    );
  });

  it("rejects an untrusted run response with an actionable boundary error", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ id: "run-1", status: "mystery" }));
    const client = createProspectClient({ fetcher, tenantId: "demo", repId: "rep" });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });
});
