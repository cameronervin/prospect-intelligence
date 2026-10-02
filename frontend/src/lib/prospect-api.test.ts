import { describe, expect, it, vi } from "vitest";

import { createProspectClient, ProspectApiError } from "@/lib/prospect-api";

const reviewBrief = {
  summary: "A supported lane fit.",
  recommended_next_step: "Discuss the lane.",
  recommended_next_step_code: "new_lane_pitch",
  modeled_annual_revenue: 1000,
  deadhead_miles_avoided: 100,
  lanes: [],
};

describe("prospect API boundary", () => {
  it("does not send browser-controlled identity headers when a run is created", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "queued",
        stage: "Preparing research",
        progress_percent: 0,
        source_coverage: [],
        evidence: [],
      }),
    );
    const client = createProspectClient({ fetcher });

    await client.startRun("acct-1");

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/prospect-runs",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: "acct-1" }),
      }),
    );
  });

  it("rejects an untrusted run response with an actionable boundary error", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ id: "run-1", status: "mystery" }));
    const client = createProspectClient({ fetcher });

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
        evidence: [],
        verdict: null,
        brief: null,
        outreach: null,
        pending_review: null,
        error: null,
      }),
    );
    const client = createProspectClient({ fetcher });

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
        evidence: [],
        verdict: "fit",
        brief: reviewBrief,
        outreach: { subject: "Freight conversation", body: "Could we discuss your freight needs?" },
        pending_review: {
          name: "send_outreach",
          allowed_decisions: ["approve", "edit", "reject"],
          tool_call_id: "review-run-1",
        },
      }),
    );
    const client = createProspectClient({ fetcher });

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
        evidence: [],
        verdict: "fit",
        brief: reviewBrief,
        outreach: { subject: "Freight conversation", body: "Could we discuss your freight needs?" },
        pending_review: null,
      }),
    );
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });

  it("rejects a durable review capability without its renderable brief and outreach", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "awaiting_review",
        stage: "Ready for review",
        progress_percent: 100,
        source_coverage: [],
        evidence: [],
        verdict: "fit",
        brief: null,
        outreach: null,
        pending_review: {
          name: "send_outreach",
          allowed_decisions: ["approve", "edit", "reject"],
          tool_call_id: "review-run-1",
        },
      }),
    );
    const client = createProspectClient({ fetcher });

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
            issues: [{ location: "body.account_id", message: "Invalid", type: "pattern" }],
          },
        },
        { status: 422 },
      ),
    );
    const client = createProspectClient({ fetcher });

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
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toMatchObject({
      code: "service_unavailable",
      retryable: true,
    });
  });

  it("parses lane score components and coverage source modes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "completed",
        stage: "No network fit found",
        progress_percent: 100,
        source_coverage: [
          { source: "FAF5.7.1 snapshot", status: "complete", detail: null, mode: "snapshot" },
          { source: "Legacy source", status: "degraded" },
        ],
        evidence: [],
        verdict: "no_fit",
        brief: {
          summary: "No fit.",
          recommended_next_step: "Do not pursue.",
          recommended_next_step_code: "not_a_fit",
          modeled_annual_revenue: 0,
          deadhead_miles_avoided: 0,
          lanes: [
            {
              origin: "Atlanta, GA",
              destination: "Dallas, TX",
              shipper_loads_per_week: 4,
              matched_loads_per_week: 1,
              fit_score: 0.5,
              backhaul_fill: 0.4,
              density: 0.6,
              equipment_match: 0.6,
              modeled_annual_revenue: 1000,
              deadhead_miles_avoided: 100,
              evidence: [],
            },
          ],
        },
      }),
    );
    const client = createProspectClient({ fetcher });

    const run = await client.getRun("run-1");

    expect(run.source_coverage.map((item) => item.mode ?? null)).toEqual(["snapshot", null]);
    expect(run.brief?.lanes[0]).toMatchObject({
      backhaul_fill: 0.4,
      density: 0.6,
      equipment_match: 0.6,
    });
  });

  it("parses citation-backed run evidence and rejects evidence without an opaque citation", async () => {
    const response = {
      id: "run-1",
      account: { id: "acct-1", name: "Atlas Foods" },
      status: "completed",
      stage: "Research complete",
      progress_percent: 100,
      source_coverage: [{ source: "Web research", status: "complete", mode: "live" }],
      evidence: [
        {
          citation_id: "ev_111111111111111111111111",
          claim: "Atlas operates a regional distribution network.",
          source: "Web research",
          mode: "live",
          endpoint_or_artifact: "https://example.test/atlas",
          retrieved_at: "2026-09-30T12:00:00Z",
          source_version: "page-v1",
          evidence_location: "paragraph:2",
        },
      ],
      verdict: "no_fit",
      brief: reviewBrief,
    } as const;
    const validFetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(response));

    await expect(
      createProspectClient({ fetcher: validFetcher }).getRun("run-1"),
    ).resolves.toMatchObject({
      evidence: [{ citation_id: "ev_111111111111111111111111", source: "Web research" }],
    });

    const uncited = { ...response.evidence[0], citation_id: undefined };
    const invalidFetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ ...response, evidence: [uncited] }));
    await expect(createProspectClient({ fetcher: invalidFetcher }).getRun("run-1")).rejects.toThrow(
      "invalid response",
    );

    const withoutEvidence = { ...response, evidence: undefined };
    const missingFetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(withoutEvidence));
    await expect(createProspectClient({ fetcher: missingFetcher }).getRun("run-1")).rejects.toThrow(
      "invalid response",
    );
  });

  it("parses repeated drafting and quality-review attempts as actual history", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "awaiting_review",
        stage: "Ready for review",
        progress_percent: 100,
        source_coverage: [],
        evidence: [],
        verdict: "fit",
        brief: reviewBrief,
        outreach: { subject: "Freight conversation", body: "Could we discuss freight needs?" },
        pending_review: {
          name: "send_outreach",
          allowed_decisions: ["approve", "edit", "reject"],
          tool_call_id: "review-run-1",
        },
        steps: [
          {
            key: "outreach-drafter:1",
            label: "Drafting outreach",
            status: "complete",
            activity: [],
          },
          {
            key: "quality-reviewer:1",
            label: "Quality review",
            status: "complete",
            activity: [],
          },
          {
            key: "outreach-drafter:2",
            label: "Drafting outreach",
            status: "complete",
            activity: [],
          },
          {
            key: "quality-reviewer:2",
            label: "Quality review",
            status: "complete",
            activity: [],
          },
          {
            key: "outreach-drafter:3",
            label: "Drafting outreach",
            status: "complete",
            activity: [],
          },
          {
            key: "quality-reviewer:3",
            label: "Quality review",
            status: "complete",
            activity: [],
          },
          { key: "review", label: "Your review", status: "running", activity: [] },
        ],
      }),
    );
    const client = createProspectClient({ fetcher });

    const response = await client.getRun("run-1");

    expect(response.steps?.map(({ key, label }) => [key, label])).toEqual([
      ["outreach-drafter:1", "Drafting outreach"],
      ["quality-reviewer:1", "Quality review"],
      ["outreach-drafter:2", "Drafting outreach"],
      ["quality-reviewer:2", "Quality review"],
      ["outreach-drafter:3", "Drafting outreach"],
      ["quality-reviewer:3", "Quality review"],
      ["review", "Your review"],
    ]);
  });

  it("rejects progress attempts whose fixed label could expose internal content", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "running",
        stage: "Reviewing",
        progress_percent: 80,
        source_coverage: [],
        evidence: [],
        steps: [
          {
            key: "quality-reviewer:1",
            label: "Revise the unsupported revenue claim",
            status: "running",
            activity: [],
          },
        ],
      }),
    );
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });

  it("rejects unknown progress keys at the API boundary", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "running",
        stage: "Reviewing",
        progress_percent: 80,
        source_coverage: [],
        evidence: [],
        steps: [
          {
            key: "quality-reviewer:4",
            label: "Quality review",
            status: "running",
            activity: [],
          },
        ],
      }),
    );
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });

  it.each([
    [{ at: "not-a-date", source: "SEC EDGAR filings", outcome: "ok" }],
    [{ at: "2026-09-30T14:02:02Z", source: "Raw prompt content", outcome: "ok" }],
  ])("rejects unsafe or malformed progress activity", async (activity) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "running",
        stage: "Researching",
        progress_percent: 20,
        source_coverage: [],
        evidence: [],
        steps: [
          {
            key: "external-research",
            label: "External research",
            status: "running",
            activity,
          },
        ],
      }),
    );
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });

  it("rejects an unknown source coverage mode at the boundary", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        id: "run-1",
        account: { id: "acct-1", name: "Atlas Foods" },
        status: "running",
        stage: "Researching",
        progress_percent: 20,
        source_coverage: [{ source: "CRM", status: "complete", mode: "scraped" }],
        evidence: [],
      }),
    );
    const client = createProspectClient({ fetcher });

    await expect(client.getRun("run-1")).rejects.toThrow("invalid response");
  });
});
