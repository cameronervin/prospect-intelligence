import type { Brief, ProspectRun, SourceCoverage, SourceMode } from "@/lib/prospect-api";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumSignificantDigits: 3,
});
const wholeNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const compactNumber = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumSignificantDigits: 3,
});
const retrievedDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const retrievedTimestamp = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export const formatCurrency = (value: number) => currency.format(value);
export const formatCompactCurrency = (value: number) => compactCurrency.format(value);
export const formatNumber = (value: number) => wholeNumber.format(value);
export const formatCompactMiles = (value: number) => `${compactNumber.format(value)} mi`;
export const formatMiles = (value: number) => `${wholeNumber.format(value)} mi`;
export const formatScore = (value: number) => value.toFixed(2);

export function formatRetrievedDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : retrievedDate.format(date);
}

export function formatRetrievedTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `${retrievedTimestamp.format(date)} UTC`;
}

/** The most recent evidence retrieval dates the brief as a whole. */
export function briefDate(brief: Brief): string | undefined {
  const times = brief.lanes
    .flatMap((lane) => lane.evidence.map((item) => Date.parse(item.retrieved_at)))
    .filter((time) => !Number.isNaN(time));
  return times.length > 0 ? new Date(Math.max(...times)).toISOString() : undefined;
}

const sourceModeLabel: Partial<Record<SourceMode, string>> = {
  live: "Live",
  snapshot: "Snapshot",
};

/** Fixture provenance remains in the source name and artifact path without a redundant mode label. */
export function visibleSourceModeLabel(mode: SourceMode): string | undefined {
  return mode === "fixture" ? undefined : sourceModeLabel[mode];
}

export const coverageStatusLabel: Record<SourceCoverage["status"], string> = {
  complete: "Complete",
  degraded: "Degraded",
  unavailable: "Unavailable",
};

export const runStatusLabel: Record<ProspectRun["status"], string> = {
  queued: "Queued",
  running: "Running",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
};

export const verdictLabel: Record<NonNullable<ProspectRun["verdict"]>, string> = {
  fit: "Network fit",
  no_fit: "No network fit",
  needs_more_data: "Needs more data",
};

export const recommendedActionLabel: Record<Brief["recommended_next_step_code"], string> = {
  expand_existing_lanes: "Expand existing lanes",
  new_lane_pitch: "Pitch new lanes",
  not_a_fit: "Not a fit",
  needs_more_data: "Gather more freight data",
};

export function isActive(status: ProspectRun["status"]): boolean {
  return status === "queued" || status === "running";
}
