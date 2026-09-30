"use client";

import { useId } from "react";

import { AgentRunSummary, AgentTracker } from "@/components/console/agent-tracker";
import { BriefPanel, ModelAssumptions, WhySummary } from "@/components/console/brief-panel";
import {
  briefDate,
  formatRetrievedDate,
  isActive,
  runStatusLabel,
} from "@/components/console/format";
import { LaneTable } from "@/components/console/lane-table";
import { ReviewCheckpoint } from "@/components/console/review-checkpoint";
import { ReviewOutcome } from "@/components/console/review-pane";
import { SourceCoverage } from "@/components/console/source-coverage";
import { StatusPill, type StatusTone } from "@/components/console/status-pill";
import type { RunReview } from "../api/client";
import type { ProspectRun } from "../api/schemas";
import { MAX_POLL_RETRIES } from "../run/constants";

const statusTone: Record<ProspectRun["status"], StatusTone> = {
  queued: "neutral",
  running: "active",
  awaiting_review: "review",
  completed: "ready",
  rejected: "neutral",
  failed: "danger",
};

function awaitingDecision(run: ProspectRun) {
  return (
    run.status === "awaiting_review" &&
    Boolean(run.pending_review) &&
    Boolean(run.outreach) &&
    run.verdict === "fit"
  );
}

export function RunView({
  run,
  pollPaused,
  decided,
  onResume,
  onDecision,
  onRefresh,
}: Readonly<{
  run: ProspectRun;
  pollPaused: boolean;
  decided: boolean;
  onResume: () => void;
  onDecision: (review: RunReview) => Promise<void>;
  onRefresh: () => Promise<void>;
}>) {
  const active = isActive(run.status);
  const dated = run.brief ? briefDate(run.brief) : undefined;
  const evidenceId = useId();
  const evidenceHeadingId = useId();
  const deciding = awaitingDecision(run);
  const hasLanes = Boolean(run.brief && run.brief.lanes.length > 0);
  const steps = run.steps ?? [];

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="type-display">{run.account.name}</h2>
          <StatusPill
            tone={
              run.status === "completed" && run.verdict !== "fit"
                ? "neutral"
                : statusTone[run.status]
            }
          >
            {deciding ? "Awaiting your review" : runStatusLabel[run.status]}
          </StatusPill>
        </div>
        <p className="type-utility">
          <span role="status" aria-label="Run progress" aria-live="polite">
            {run.stage}
          </span>
          {active ? <span aria-hidden="true">{` · ${run.progress_percent}%`}</span> : null}
          {!active && dated ? ` · Evidence as of ${formatRetrievedDate(dated)}` : ""}
        </p>
        {active ? (
          <progress
            className="meter"
            max={100}
            value={run.progress_percent}
            aria-label="Research progress"
          />
        ) : null}
        {!active ? <AgentRunSummary steps={steps} /> : null}
      </header>

      {active && steps.length > 0 ? <AgentTracker steps={steps} /> : null}

      {pollPaused ? (
        <div role="alert" className="alert">
          <p className="font-semibold">Progress updates paused</p>
          <p className="type-utility text-foreground-soft">
            We couldn&apos;t reach the service after {MAX_POLL_RETRIES} retries. Research continues
            on the server.
          </p>
          <div className="mt-1.5">
            <button type="button" className="btn-secondary" onClick={onResume}>
              Resume updates
            </button>
          </div>
        </div>
      ) : null}

      {run.status === "failed" ? (
        <div role="alert" className="alert">
          <p className="font-semibold">Research could not be completed</p>
          <p className="type-utility text-foreground-soft">
            No customer-facing output was produced. Run the prospect agent again to retry.
          </p>
        </div>
      ) : null}

      {deciding && run.outreach && run.pending_review && run.brief && run.verdict ? (
        <ReviewCheckpoint
          key={run.id}
          accountName={run.account.name}
          outreach={run.outreach}
          toolCallId={run.pending_review.tool_call_id}
          onDecision={onDecision}
          onRefresh={onRefresh}
          rationale={<WhySummary brief={run.brief} verdict={run.verdict} evidenceId={evidenceId} />}
        />
      ) : null}

      {!deciding ? <ReviewOutcome run={run} decided={decided} /> : null}
      {!deciding && run.brief && run.verdict ? (
        <BriefPanel brief={run.brief} verdict={run.verdict} />
      ) : null}

      <section
        id={evidenceId}
        aria-labelledby={hasLanes ? evidenceHeadingId : undefined}
        aria-label={hasLanes ? undefined : "Research evidence"}
        className="flex scroll-mt-4 flex-col gap-4"
      >
        {hasLanes ? (
          <div className="flex flex-wrap items-center gap-x-4">
            <h2 id={evidenceHeadingId} className="type-title">
              Supporting evidence
            </h2>
            <ModelAssumptions />
          </div>
        ) : null}
        {run.brief && hasLanes ? <LaneTable lanes={run.brief.lanes} /> : null}
        <SourceCoverage coverage={run.source_coverage} />
      </section>
    </div>
  );
}
