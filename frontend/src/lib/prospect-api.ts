import { z } from "zod";

const AccountSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  relationship: z.enum(["Prospect", "Customer"]),
  industry: z.string().min(1),
  location: z.string().min(1).optional(),
});

const SourceCoverageSchema = z.object({
  source: z.string().min(1),
  status: z.enum(["pending", "complete", "degraded", "unavailable"]),
  detail: z.string().optional(),
});

const EvidenceSchema = z.object({
  claim: z.string().min(1),
  source: z.string().min(1),
  retrieved_at: z.string().min(1),
  source_version: z.string().optional(),
  evidence_location: z.string().optional(),
});

const LaneSchema = z.object({
  origin: z.string().min(1),
  destination: z.string().min(1),
  shipper_loads_per_week: z.number().nonnegative(),
  matched_loads_per_week: z.number().nonnegative(),
  fit_score: z.number().min(0).max(1),
  modeled_annual_revenue: z.number().nonnegative(),
  deadhead_miles_avoided: z.number().nonnegative(),
  evidence: z.array(EvidenceSchema),
});

const BriefSchema = z.object({
  summary: z.string().min(1),
  recommended_next_step: z.string().min(1),
  modeled_annual_revenue: z.number().nonnegative(),
  deadhead_miles_avoided: z.number().nonnegative(),
  lanes: z.array(LaneSchema),
});

const OutreachSchema = z.object({
  subject: z.string(),
  body: z.string(),
  tool_call_id: z.string().min(1).optional(),
});

const RunSchema = z.object({
  id: z.string().min(1),
  account: z.object({ id: z.string().min(1), name: z.string().min(1) }),
  status: z.enum(["queued", "running", "awaiting_review", "completed", "rejected", "failed"]),
  stage: z.string().min(1),
  progress_percent: z.number().min(0).max(100),
  source_coverage: z.array(SourceCoverageSchema),
  verdict: z.enum(["fit", "no_fit", "needs_more_data"]).optional(),
  brief: BriefSchema.optional(),
  outreach: OutreachSchema.optional(),
  error: z.string().optional(),
});

const AccountsSchema = z.object({ items: z.array(AccountSchema) });

export type Account = z.infer<typeof AccountSchema>;
export type ProspectRun = z.infer<typeof RunSchema>;
export type RunReview = {
  decision: "approve" | "edit" | "reject";
  subject?: string;
  body?: string;
  tool_call_id: string;
};

export interface ProspectClient {
  listAccounts(): Promise<Account[]>;
  startRun(accountId: string): Promise<ProspectRun>;
  getRun(runId: string): Promise<ProspectRun>;
  reviewRun(runId: string, review: RunReview): Promise<ProspectRun>;
}

type ClientOptions = {
  fetcher?: typeof fetch;
  tenantId: string;
  repId: string;
};

export class ProspectApiError extends Error {
  constructor(message = "The prospect service is unavailable") {
    super(message);
    this.name = "ProspectApiError";
  }
}

export function createProspectClient({
  fetcher = fetch,
  tenantId,
  repId,
}: ClientOptions): ProspectClient {
  const headers = {
    "Content-Type": "application/json",
    "X-Tenant-Id": tenantId,
    "X-Rep-Id": repId,
  };

  async function request<T>(path: string, init: RequestInit, schema: z.ZodType<T>): Promise<T> {
    let response: Response;
    try {
      response = await fetcher(path, { ...init, headers: { ...headers, ...init.headers } });
    } catch {
      throw new ProspectApiError();
    }
    if (!response.ok) {
      throw new ProspectApiError(`The prospect service returned ${response.status}`);
    }
    try {
      return schema.parse(await response.json());
    } catch {
      throw new ProspectApiError("The prospect service returned an invalid response");
    }
  }

  return {
    async listAccounts() {
      return (await request("/api/v1/accounts", { method: "GET" }, AccountsSchema)).items;
    },
    startRun(accountId) {
      return request(
        "/api/v1/prospect-runs",
        { method: "POST", body: JSON.stringify({ account_id: accountId }) },
        RunSchema,
      );
    },
    getRun(runId) {
      return request(
        `/api/v1/prospect-runs/${encodeURIComponent(runId)}`,
        { method: "GET" },
        RunSchema,
      );
    },
    reviewRun(runId, review) {
      return request(
        `/api/v1/prospect-runs/${encodeURIComponent(runId)}/review`,
        { method: "POST", body: JSON.stringify(review) },
        RunSchema,
      );
    },
  };
}
