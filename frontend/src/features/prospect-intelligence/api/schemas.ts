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
  at: z.iso.datetime({ offset: true }),
  source: z.enum([
    "CRM account record",
    "Carrier network lanes",
    "GenLogs freight activity",
    "SEC EDGAR filings",
    "Web research",
    "FMCSA carrier registry",
    "FAF5 market volume",
    "lane_fit_v1 scoring",
  ]),
  outcome: z.enum(["ok", "unavailable"]),
});
const fixedStepLabels: Readonly<Record<string, string>> = {
  "account-context": "Account context",
  "external-research": "External research",
  "lane-analyst": "Lane analysis",
  review: "Your review",
};
const RunStepSchema = z
  .object({
    key: z.string().min(1),
    label: z.string().min(1),
    status: z.enum(["pending", "running", "complete", "failed", "skipped"]),
    started_at: z.string().nullable().optional(),
    finished_at: z.string().nullable().optional(),
    activity: z.array(StepActivitySchema),
  })
  .superRefine((step, context) => {
    const attempt = /^(outreach-drafter|quality-reviewer):[1-3]$/.exec(step.key)?.[1];
    const expected =
      fixedStepLabels[step.key] ??
      (attempt === "outreach-drafter"
        ? "Drafting outreach"
        : attempt === "quality-reviewer"
          ? "Quality review"
          : undefined);
    if (expected === undefined) {
      context.addIssue({ code: "custom", message: "unknown public progress key", path: ["key"] });
    } else if (step.label !== expected) {
      context.addIssue({
        code: "custom",
        message: "step label does not match its public progress key",
        path: ["label"],
      });
    }
  });

const OutreachSchema = z.object({ subject: z.string(), body: z.string() });
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
export const ErrorIssueSchema = z.object({
  location: z.string(),
  message: z.string(),
  type: z.string(),
});
export const ErrorResponseSchema = z.object({
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

export const RunSchema = z
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
  })
  .refine(
    (run) =>
      run.status !== "awaiting_review" ||
      (run.verdict === "fit" && Boolean(run.brief) && Boolean(run.outreach)),
    {
      message: "awaiting-review runs must include a fit brief and outreach draft",
      path: ["status"],
    },
  );

export const AccountsSchema = z.object({ items: z.array(AccountSchema) });

export type Account = z.infer<typeof AccountSchema>;
export type ProspectRun = z.infer<typeof RunSchema>;
export type Brief = z.infer<typeof BriefSchema>;
export type Lane = z.infer<typeof LaneSchema>;
export type Evidence = z.infer<typeof EvidenceSchema>;
export type SourceCoverage = z.infer<typeof SourceCoverageSchema>;
export type SourceMode = z.infer<typeof SourceModeSchema>;
export type RunStep = z.infer<typeof RunStepSchema>;
export type ProspectApiErrorCode = z.infer<typeof ErrorResponseSchema>["error"]["code"];
export type ErrorIssue = z.infer<typeof ErrorIssueSchema>;
