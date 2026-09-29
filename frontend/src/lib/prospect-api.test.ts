import { describe, expect, it, vi } from "vitest";

import { createProspectClient, ProspectApiError } from "@/lib/prospect-api";

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

  it("accepts explicit nulls for run fields that are not available yet", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "queued",
        stage: "Preparing research",
        progress_percent: 0,
        source_coverage: [],
        verdict: null,
        brief: null,
        outreach: null,
        pending_review: null,
        error: null,
      }),
    );
    const client = createProspectClient({ fetcher, tenantId: "demo", repId: "rep" });

    await expect(client.getRun("run-1")).resolves.toMatchObject({ verdict: null, error: null });
  });

  it("parses the durable review interrupt separately from draft outreach", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "awaiting_review",
        stage: "Ready for review",
        progress_percent: 100,
        source_coverage: [],
        verdict: "fit",
        outreach: { subject: "Freight conversation", body: "Could we discuss your freight needs?" },
        pending_review: {
          name: "send_outreach",
          allowed_decisions: ["approve", "edit", "reject"],
          tool_call_id: "review-run-1",
        },
      }),
    );
    const client = createProspectClient({ fetcher, tenantId: "demo", repId: "rep" });

    await expect(client.getRun("run-1")).resolves.toMatchObject({
      pending_review: {
        name: "send_outreach",
        allowed_decisions: ["approve", "edit", "reject"],
        tool_call_id: "review-run-1",
      },
    });
  });

  it("rejects an awaiting-review response without its durable review capability", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "awaiting_review",
        stage: "Ready for review",
        progress_percent: 100,
        source_coverage: [],
        verdict: "fit",
        outreach: { subject: "Freight conversation", body: "Could we discuss your freight needs?" },
        pending_review: null,
      }),
    );
    const client = createProspectClient({ fetcher, tenantId: "demo", repId: "rep" });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });

  it("parses the typed API error envelope", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          error: {
            code: "validation_error",
            message: "Request validation failed.",
            retryable: false,
            issues: [{ location: "header.X-Tenant-Id", message: "Invalid", type: "pattern" }],
          },
        },
        { status: 422 },
      ),
    );
    const client = createProspectClient({ fetcher, tenantId: "bad value", repId: "rep" });

    const error = await client.listAccounts().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ProspectApiError);
    expect(error).toMatchObject({ code: "validation_error", retryable: false });
  });

  it("preserves retryable service-unavailable errors for review retries", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          error: {
            code: "service_unavailable",
            message: "Review service is temporarily unavailable.",
            retryable: true,
            issues: [],
          },
        },
        { status: 503 },
      ),
    );
    const client = createProspectClient({ fetcher, tenantId: "demo", repId: "rep" });

    await expect(client.getRun("run-1")).rejects.toMatchObject({
      code: "service_unavailable",
      retryable: true,
    });
  });
});
