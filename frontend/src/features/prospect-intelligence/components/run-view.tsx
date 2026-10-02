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
import { alertStyle, buttonStyles, typeStyles } from "@/components/ui/styles";
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
  const evidenceTimes = run.evidence
    .map((item) => Date.parse(item.retrieved_at))
    .filter((time) => !Number.isNaN(time));
  const dated =
    evidenceTimes.length > 0
      ? new Date(Math.max(...evidenceTimes)).toISOString()
      : run.brief
        ? briefDate(run.brief)
        : undefined;
  const evidenceId = useId();
  const evidenceHeadingId = useId();
  const deciding = awaitingDecision(run);
  const completedFit = run.status === "completed" && run.verdict === "fit";
  const hasLanes = Boolean(run.brief && run.brief.lanes.length > 0);
  const steps = run.steps ?? [];

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className={typeStyles.display}>{run.account.name}</h2>
          {!active ? (
            <StatusPill
              tone={
                run.status === "completed" && run.verdict !== "fit"
                  ? "neutral"
                  : statusTone[run.status]
              }
            >
              {deciding ? "Awaiting your review" : runStatusLabel[run.status]}
            </StatusPill>
          ) : null}
        </div>
        {active ? (
          <p className={typeStyles.utility}>
            <span role="status" aria-label="Run progress" aria-live="polite">
              {run.stage}
            </span>
            <span aria-hidden="true">{` · ${run.progress_percent}%`}</span>
          </p>
        ) : !deciding && !completedFit ? (
          <p className={typeStyles.utility}>{run.stage}</p>
        ) : null}
        {active ? (
          <progress
            className="meter meter-active"
            max={100}
            value={run.progress_percent}
            aria-label="Research progress"
            data-agent-motion="progress-meter"
          />
        ) : null}
        {!active ? (
          <AgentRunSummary
            steps={steps}
            metadata={
              dated ? (
                <span className={`${typeStyles.utility} self-center`}>
                  {`Evidence as of ${formatRetrievedDate(dated)}`}
                </span>
              ) : undefined
            }
          />
        ) : null}
      </header>

      {active && steps.length > 0 ? <AgentTracker steps={steps} /> : null}

      {pollPaused ? (
        <div role="alert" className={alertStyle}>
          <p className="font-semibold">Progress updates paused</p>
          <p className={typeStyles.utility}>
            We couldn&apos;t reach the service after {MAX_POLL_RETRIES} retries. Research continues
            on the server.
          </p>
          <div className="mt-1.5">
            <button type="button" className={buttonStyles.secondary} onClick={onResume}>
              Resume updates
            </button>
          </div>
        </div>
      ) : null}

      {run.status === "failed" ? (
        <div role="alert" className={alertStyle}>
          <p className="font-semibold">Research could not be completed</p>
          <p className={typeStyles.utility}>
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
        <BriefPanel
          brief={run.brief}
          verdict={run.verdict}
          showRecommendedNextStep={!completedFit}
        />
      ) : null}

      <section
        id={evidenceId}
        aria-labelledby={hasLanes ? evidenceHeadingId : undefined}
        aria-label={hasLanes ? undefined : "Research evidence"}
        className="flex scroll-mt-4 flex-col gap-4"
      >
        {hasLanes ? (
          <div className="flex flex-wrap items-center gap-x-4">
            <h2 id={evidenceHeadingId} className={typeStyles.title}>
              Supporting evidence
            </h2>
            <ModelAssumptions />
          </div>
        ) : null}
        {run.brief && hasLanes ? <LaneTable lanes={run.brief.lanes} /> : null}
        <SourceCoverage coverage={run.source_coverage} evidence={run.evidence} />
      </section>
    </div>
  );
}
