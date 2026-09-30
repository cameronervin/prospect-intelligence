"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { AccountRail, type AccountsState } from "@/components/console/account-rail";
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
import { DEMO_REP_ID, DEMO_TENANT_ID } from "@/lib/demo-identity";
import {
  createProspectClient,
  type Account,
  type ProspectClient,
  type ProspectRun,
  type RunReview,
} from "@/lib/prospect-api";

/** Automatic poll retries after a failure, with exponential backoff, before pausing. */
export const MAX_POLL_RETRIES = 3;

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

function RunView({
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

export function ProspectWorkspace({
  client,
  pollIntervalMs = 1200,
}: Readonly<{ client?: ProspectClient; pollIntervalMs?: number }>) {
  const api = useMemo(
    () => client ?? createProspectClient({ tenantId: DEMO_TENANT_ID, repId: DEMO_REP_ID }),
    [client],
  );
  const [accounts, setAccounts] = useState<AccountsState>({ kind: "loading" });
  const [selected, setSelected] = useState<Account>();
  const [run, setRun] = useState<ProspectRun>();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState(false);
  const [pollFailures, setPollFailures] = useState(0);
  const [pollPaused, setPollPaused] = useState(false);
  const [decided, setDecided] = useState(false);
  const [deciding, setDeciding] = useState(false);
  // The run currently on screen; responses for any other run are dropped.
  const currentRunId = useRef<string | undefined>(undefined);

  const fetchAccounts = useCallback(
    () =>
      api.listAccounts().then(
        (items): AccountsState => ({ kind: "ready", accounts: items }),
        (): AccountsState => ({ kind: "error" }),
      ),
    [api],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchAccounts().then((next) => {
      if (!cancelled) setAccounts(next);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchAccounts]);

  function reloadAccounts() {
    setAccounts({ kind: "loading" });
    void fetchAccounts().then(setAccounts);
  }

  function show(next: ProspectRun | undefined) {
    currentRunId.current = next?.id;
    setRun(next);
  }

  useEffect(() => {
    if (!run || !isActive(run.status) || pollPaused) return;
    let cancelled = false;
    const timer = setTimeout(
      async () => {
        try {
          const next = await api.getRun(run.id);
          if (cancelled) return;
          setPollFailures(0);
          setRun(next);
        } catch {
          if (cancelled) return;
          if (pollFailures >= MAX_POLL_RETRIES) setPollPaused(true);
          else setPollFailures(pollFailures + 1);
        }
      },
      pollIntervalMs * 2 ** pollFailures,
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, run, pollFailures, pollPaused, pollIntervalMs]);

  function resetRunState() {
    setPollFailures(0);
    setPollPaused(false);
    setDecided(false);
  }

  async function startBrief() {
    if (!selected) return;
    setStarting(true);
    setStartError(false);
    resetRunState();
    try {
      show(await api.startRun(selected.id));
    } catch {
      setStartError(true);
    } finally {
      setStarting(false);
    }
  }

  async function decide(review: RunReview) {
    if (!run) return;
    const runId = run.id;
    setDeciding(true);
    try {
      const next = await api.reviewRun(runId, review);
      if (currentRunId.current !== runId) return;
      setDecided(true);
      setRun(next);
    } finally {
      setDeciding(false);
    }
  }

  async function refresh() {
    if (!run) return;
    const runId = run.id;
    const next = await api.getRun(runId);
    if (currentRunId.current !== runId) return;
    setDecided(true);
    setRun(next);
  }

  const locked = starting || deciding || Boolean(run && isActive(run.status));

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] grid-cols-1 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <AccountRail
        state={accounts}
        selectedId={selected?.id}
        locked={locked}
        starting={starting}
        startError={startError}
        quiet={Boolean(run)}
        onSelect={(account) => {
          setSelected(account);
          setStartError(false);
          if (run && run.account.id !== account.id) {
            show(undefined);
            resetRunState();
          }
        }}
        onStart={() => void startBrief()}
        running={Boolean(run && isActive(run.status))}
        onRetry={reloadAccounts}
        onReload={reloadAccounts}
      />

      <section aria-label="Workspace" className="min-w-0 px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-[72rem]">
          {run ? (
            <RunView
              run={run}
              pollPaused={pollPaused}
              decided={decided}
              onResume={() => {
                setPollFailures(0);
                setPollPaused(false);
              }}
              onDecision={decide}
              onRefresh={refresh}
            />
          ) : (
            <div className="border-line-strong max-w-xl rounded border border-dashed px-4 py-5">
              <p className="text-sm font-semibold">Select an account to run the prospect agent</p>
              <p className="type-utility mt-1">
                Four specialist agents research the account, score lanes against your network, and
                draft outreach. You watch each step here and review the message before anything is
                sent.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
