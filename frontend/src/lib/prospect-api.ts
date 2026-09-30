import { z } from "zod";

const AccountSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  relationship: z.enum(["Prospect", "Customer"]),
  industry: z.string().min(1),
  location: z.string().min(1).nullable().optional(),
});

const SourceModeSchema = z.enum(["live", "fixture", "snapshot"]);

const SourceCoverageSchema = z.object({
  source: z.string().min(1),
  status: z.enum(["complete", "degraded", "unavailable"]),
  detail: z.string().nullable().optional(),
  mode: SourceModeSchema.nullable().optional(),
});

const EvidenceSchema = z.object({
  claim: z.string().min(1),
  source: z.string().min(1),
  mode: SourceModeSchema,
  endpoint_or_artifact: z.string().min(1),
  retrieved_at: z.string().min(1),
  source_version: z.string().min(1),
  evidence_location: z.string().min(1),
});

const LaneSchema = z.object({
  origin: z.string().min(1),
  destination: z.string().min(1),
  shipper_loads_per_week: z.number().nonnegative(),
  matched_loads_per_week: z.number().nonnegative(),
  fit_score: z.number().min(0).max(1),
  backhaul_fill: z.number().min(0).max(1),
  density: z.number().min(0).max(1),
  equipment_match: z.number().min(0).max(1),
  modeled_annual_revenue: z.number().nonnegative(),
  deadhead_miles_avoided: z.number().nonnegative(),
  evidence: z.array(EvidenceSchema),
});

const BriefSchema = z.object({
  summary: z.string().min(1),
  recommended_next_step: z.string().min(1),
  recommended_next_step_code: z.enum([
    "expand_existing_lanes",
    "new_lane_pitch",
    "not_a_fit",
    "needs_more_data",
  ]),
  modeled_annual_revenue: z.number().nonnegative(),
  deadhead_miles_avoided: z.number().nonnegative(),
  lanes: z.array(LaneSchema),
});

const StepActivitySchema = z.object({
  at: z.string().min(1),
  source: z.string().min(1),
  outcome: z.enum(["ok", "unavailable"]),
});

const RunStepSchema = z.object({
  key: z.string().min(1),
  label: z.string().min(1),
  status: z.enum(["pending", "running", "complete", "failed", "skipped"]),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  activity: z.array(StepActivitySchema),
});

const OutreachSchema = z.object({
  subject: z.string(),
  body: z.string(),
});

const PendingReviewSchema = z.object({
  name: z.literal("send_outreach"),
  allowed_decisions: z.tuple([z.literal("approve"), z.literal("edit"), z.literal("reject")]),
  tool_call_id: z.string().min(1),
});

const RunErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  retryable: z.boolean(),
});

const ErrorIssueSchema = z.object({
  location: z.string(),
  message: z.string(),
  type: z.string(),
});

const ErrorResponseSchema = z.object({
  error: z.object({
    code: z.enum([
      "validation_error",
      "not_found",
      "conflict",
      "internal_error",
      "service_unavailable",
    ]),
    message: z.string().min(1),
    retryable: z.boolean(),
    issues: z.array(ErrorIssueSchema),
  }),
});

const RunSchema = z
  .object({
    id: z.string().min(1),
    account: z.object({ id: z.string().min(1), name: z.string().min(1) }),
    status: z.enum(["queued", "running", "awaiting_review", "completed", "rejected", "failed"]),
    stage: z.string().min(1),
    progress_percent: z.number().min(0).max(100),
    steps: z.array(RunStepSchema).optional(),
    source_coverage: z.array(SourceCoverageSchema),
    verdict: z.enum(["fit", "no_fit", "needs_more_data"]).nullable().optional(),
    brief: BriefSchema.nullable().optional(),
    outreach: OutreachSchema.nullable().optional(),
    pending_review: PendingReviewSchema.nullable().optional(),
    error: RunErrorSchema.nullable().optional(),
  })
  .refine((run) => (run.status === "awaiting_review") === Boolean(run.pending_review), {
    message: "pending_review must match awaiting-review status",
    path: ["pending_review"],
  });

const AccountsSchema = z.object({ items: z.array(AccountSchema) });

export type Account = z.infer<typeof AccountSchema>;
export type ProspectRun = z.infer<typeof RunSchema>;
export type Brief = z.infer<typeof BriefSchema>;
export type Lane = z.infer<typeof LaneSchema>;
export type Evidence = z.infer<typeof EvidenceSchema>;
export type SourceCoverage = z.infer<typeof SourceCoverageSchema>;
export type SourceMode = z.infer<typeof SourceModeSchema>;
export type RunStep = z.infer<typeof RunStepSchema>;
export type ProspectApiErrorCode = z.infer<typeof ErrorResponseSchema>["error"]["code"];
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
  readonly code?: ProspectApiErrorCode;
  readonly retryable?: boolean;
  readonly issues: z.infer<typeof ErrorIssueSchema>[];

  constructor(
    message = "The prospect service is unavailable",
    options: {
      code?: ProspectApiErrorCode;
      retryable?: boolean;
      issues?: z.infer<typeof ErrorIssueSchema>[];
    } = {},
  ) {
    super(message);
    this.name = "ProspectApiError";
    this.code = options.code;
    this.retryable = options.retryable;
    this.issues = options.issues ?? [];
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
      const payload = await response
        .json()
        .then((body: unknown) => ErrorResponseSchema.safeParse(body))
        .catch(() => undefined);
      if (payload?.success) {
        throw new ProspectApiError(payload.data.error.message, {
          code: payload.data.error.code,
          retryable: payload.data.error.retryable,
          issues: payload.data.error.issues,
        });
      }
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
