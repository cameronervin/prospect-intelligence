"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createProspectClient,
  type Account,
  type ProspectClient,
  type ProspectRun,
  type RunReview,
} from "@/lib/prospect-api";

const DEMO_TENANT = "tenant-demo";
const DEMO_REP = "maya-chen";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function AccountPicker({
  accounts,
  selectedId,
  disabled,
  onSelect,
}: Readonly<{
  accounts: Account[];
  selectedId?: string;
  disabled: boolean;
  onSelect: (account: Account) => void;
}>) {
  return (
    <div className="grid gap-3" aria-label="Assigned shipper accounts">
      {accounts.map((account) => {
        const selected = selectedId === account.id;
        return (
          <button
            key={account.id}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            onClick={() => onSelect(account)}
            className={`group rounded-2xl border p-4 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none ${
              selected
                ? "border-accent bg-accent/[0.07] shadow-[inset_3px_0_0_var(--accent)]"
                : "border-border bg-card hover:border-foreground/30"
            }`}
          >
            <span className="flex items-start justify-between gap-3">
              <span>
                <span className="block font-semibold">{account.name}</span>
                <span className="mt-1 block text-sm text-muted-foreground">
                  {account.industry}
                  {account.location ? ` · ${account.location}` : ""}
                </span>
              </span>
              <span className="rounded-full bg-muted px-2.5 py-1 text-[0.68rem] font-bold tracking-wide uppercase">
                {account.relationship}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function SourceCoverage({ sources }: Readonly<{ sources: ProspectRun["source_coverage"] }>) {
  if (sources.length === 0) return null;
  return (
    <section aria-labelledby="coverage-title" className="border-t border-border pt-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-semibold" id="coverage-title">
          Source coverage
        </h3>
        <span className="text-xs text-muted-foreground">Live + disclosed snapshots</span>
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {sources.map((source) => (
          <li key={source.source} className="rounded-xl bg-muted/55 px-3 py-2.5 text-sm">
            <span className="flex items-center justify-between gap-3">
              <span className="font-medium">{source.source}</span>
              <span
                className={
                  source.status === "complete"
                    ? "text-ready"
                    : source.status === "pending"
                      ? "text-muted-foreground"
                      : "text-degraded"
                }
              >
                {source.status}
              </span>
            </span>
            {source.detail ? (
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                {source.detail}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function LaneCards({ lanes }: Readonly<{ lanes: NonNullable<ProspectRun["brief"]>["lanes"] }>) {
  return (
    <ol className="mt-5 grid gap-3">
      {lanes.slice(0, 3).map((lane, index) => (
        <li
          key={`${lane.origin}-${lane.destination}`}
          className="rounded-2xl border border-border bg-card p-5"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold tracking-[0.14em] text-muted-foreground uppercase">
                Priority {index + 1}
              </p>
              <h4 className="mt-1 text-lg font-semibold">
                {lane.origin} → {lane.destination}
              </h4>
            </div>
            <span className="rounded-full bg-ready/10 px-3 py-1 text-sm font-bold text-ready">
              {Math.round(lane.fit_score * 100)}% fit
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Shipper volume</dt>
              <dd className="mt-1 font-semibold">{lane.shipper_loads_per_week}/wk</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Matched loads</dt>
              <dd className="mt-1 font-semibold">{lane.matched_loads_per_week}/wk</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Revenue model</dt>
              <dd className="mt-1 font-semibold">{currency.format(lane.modeled_annual_revenue)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Deadhead avoided</dt>
              <dd className="mt-1 font-semibold">
                {number.format(lane.deadhead_miles_avoided)} mi
              </dd>
            </div>
          </dl>
          {lane.evidence.length > 0 ? (
            <details className="mt-4 border-t border-border pt-3 text-sm">
              <summary className="cursor-pointer font-medium focus-visible:outline-2 focus-visible:outline-offset-2">
                Inspect evidence ({lane.evidence.length})
              </summary>
              <ul className="mt-3 grid gap-2 text-muted-foreground">
                {lane.evidence.map((item) => (
                  <li key={`${item.source}-${item.claim}`}>
                    <span className="text-foreground">{item.claim}</span> — {item.source}
                    {item.source_version ? ` · ${item.source_version}` : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function VerdictPanel({ run }: Readonly<{ run: ProspectRun }>) {
  if (!run.brief) return null;
  const verdictCopy = {
    fit: { label: "Strong network fit", className: "text-ready bg-ready/10" },
    no_fit: { label: "Not a network fit", className: "text-degraded bg-degraded/10" },
    needs_more_data: { label: "More data needed", className: "text-degraded bg-degraded/10" },
  }[run.verdict ?? "needs_more_data"];

  return (
    <section aria-labelledby="brief-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">
            Research output
          </p>
          <h2 className="mt-2 text-2xl font-semibold" id="brief-title">
            Network-fit brief
          </h2>
        </div>
        <span className={`rounded-full px-3 py-1.5 text-sm font-bold ${verdictCopy.className}`}>
          {verdictCopy.label}
        </span>
      </div>
      <p className="mt-5 max-w-3xl text-lg leading-8">{run.brief.summary}</p>
      <div className="mt-5 rounded-2xl bg-foreground p-5 text-background">
        <p className="text-xs font-bold tracking-[0.15em] opacity-70 uppercase">
          Recommended next step
        </p>
        <p className="mt-2 font-semibold">{run.brief.recommended_next_step}</p>
      </div>
      {run.brief.lanes.length > 0 ? <LaneCards lanes={run.brief.lanes} /> : null}
    </section>
  );
}

function OutreachReview({
  run,
  submitting,
  onReview,
}: Readonly<{
  run: ProspectRun;
  submitting: boolean;
  onReview: (review: RunReview) => Promise<void>;
}>) {
  const [subject, setSubject] = useState(run.outreach?.subject ?? "");
  const [body, setBody] = useState(run.outreach?.body ?? "");
  const changed = subject !== run.outreach?.subject || body !== run.outreach?.body;
  const toolCallId = run.outreach?.tool_call_id ?? `review-${run.id}`;

  return (
    <section
      className="rounded-3xl border border-accent/35 bg-accent/[0.06] p-5 sm:p-7"
      aria-labelledby="review-title"
    >
      <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">Human checkpoint</p>
      <h2 className="mt-2 text-2xl font-semibold" id="review-title">
        Review outreach before send
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Nothing leaves this demo until you approve it. Sending is simulated and recorded for
        evaluation.
      </p>
      <div className="mt-5 grid gap-4">
        <label className="grid gap-2 text-sm font-semibold">
          Subject
          <input
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            className="rounded-xl border border-border bg-card px-4 py-3 font-normal text-foreground focus-visible:outline-2 focus-visible:outline-offset-2"
          />
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Message
          <textarea
            rows={7}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="resize-y rounded-xl border border-border bg-card px-4 py-3 font-normal leading-7 text-foreground focus-visible:outline-2 focus-visible:outline-offset-2"
          />
        </label>
      </div>
      <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <button
          type="button"
          disabled={submitting}
          onClick={() => onReview({ decision: "reject", tool_call_id: toolCallId })}
          className="rounded-xl border border-border bg-card px-5 py-3 font-semibold disabled:opacity-60"
        >
          Reject draft
        </button>
        <button
          type="button"
          disabled={submitting || subject.trim() === "" || body.trim() === ""}
          onClick={() =>
            onReview({
              decision: changed ? "edit" : "approve",
              subject,
              body,
              tool_call_id: toolCallId,
            })
          }
          className="rounded-xl bg-accent px-5 py-3 font-bold text-white shadow-lg shadow-accent/15 disabled:opacity-60"
        >
          {submitting ? "Recording decision…" : "Approve simulated send"}
        </button>
      </div>
    </section>
  );
}

export function ProspectWorkspace({
  client,
  pollIntervalMs = 1200,
}: Readonly<{ client?: ProspectClient; pollIntervalMs?: number }>) {
  const api = useMemo(
    () => client ?? createProspectClient({ tenantId: DEMO_TENANT, repId: DEMO_REP }),
    [client],
  );
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<Account>();
  const [run, setRun] = useState<ProspectRun>();
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [accountsError, setAccountsError] = useState(false);
  const [actionError, setActionError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    setAccountsError(false);
    try {
      const next = await api.listAccounts();
      setAccounts(next);
      setSelected((current) => current ?? next[0]);
    } catch {
      setAccountsError(true);
    } finally {
      setLoadingAccounts(false);
    }
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    api
      .listAccounts()
      .then((next) => {
        if (cancelled) return;
        setAccounts(next);
        setSelected((current) => current ?? next[0]);
      })
      .catch(() => {
        if (!cancelled) setAccountsError(true);
      })
      .finally(() => {
        if (!cancelled) setLoadingAccounts(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    if (!run || (run.status !== "queued" && run.status !== "running")) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.getRun(run.id);
        if (!cancelled) setRun(next);
      } catch {
        if (!cancelled) setActionError("Progress updates paused. Check your connection and retry.");
      }
    }, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [api, pollIntervalMs, run]);

  async function startRun() {
    if (!selected) return;
    setSubmitting(true);
    setActionError(undefined);
    try {
      setRun(await api.startRun(selected.id));
    } catch {
      setActionError("The brief could not be started. Your account selection is still available.");
    } finally {
      setSubmitting(false);
    }
  }

  async function reviewRun(review: RunReview) {
    if (!run) return;
    setSubmitting(true);
    setActionError(undefined);
    try {
      setRun(await api.reviewRun(run.id, review));
    } catch {
      setActionError("Your review was not recorded. The draft is unchanged; please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const isResearching = run?.status === "queued" || run?.status === "running";
  const canStart = selected && !isResearching && run?.status !== "awaiting_review";

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(17rem,0.72fr)_minmax(0,1.7fr)] lg:items-start">
      <aside className="grid gap-5 lg:sticky lg:top-6">
        <div>
          <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">
            Your territory
          </p>
          <h2 className="mt-2 text-xl font-semibold">Choose a shipper</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Seeded demo accounts · signed in as Maya Chen
          </p>
        </div>
        {loadingAccounts ? (
          <div
            role="status"
            className="rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground"
          >
            Loading assigned accounts…
          </div>
        ) : accountsError ? (
          <div role="alert" className="rounded-2xl border border-degraded/40 bg-degraded/10 p-5">
            <p className="font-semibold">We couldn&apos;t load your assigned accounts.</p>
            <p className="mt-2 text-sm text-muted-foreground">The workspace is safe to retry.</p>
            <button
              type="button"
              onClick={() => void loadAccounts()}
              className="mt-4 font-bold text-accent underline underline-offset-4"
            >
              Try again
            </button>
          </div>
        ) : accounts.length === 0 ? (
          <div
            role="status"
            className="rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground"
          >
            No accounts are assigned to this rep.
          </div>
        ) : (
          <AccountPicker
            accounts={accounts}
            selectedId={selected?.id}
            disabled={isResearching || run?.status === "awaiting_review"}
            onSelect={(account) => {
              setSelected(account);
              setRun(undefined);
              setActionError(undefined);
            }}
          />
        )}
        <button
          type="button"
          disabled={!canStart || submitting}
          onClick={() => void startRun()}
          className="rounded-xl bg-foreground px-5 py-3.5 font-bold text-background shadow-xl shadow-foreground/10 transition hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-45 motion-reduce:transition-none"
        >
          {submitting && !run ? "Starting research…" : "Build prospect brief"}
        </button>
      </aside>

      <div className="grid min-w-0 gap-6">
        {!run ? (
          <section
            className="overflow-hidden rounded-3xl border border-border bg-card shadow-[0_28px_90px_rgb(22_28_25_/_8%)]"
            aria-labelledby="empty-title"
          >
            <div className="border-b border-border bg-[radial-gradient(circle_at_top_right,var(--muted),transparent_60%)] p-6 sm:p-9">
              <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">
                Evidence before outreach
              </p>
              <h2
                id="empty-title"
                className="mt-3 max-w-xl text-[clamp(2rem,5vw,3.4rem)] leading-[1.02] font-semibold tracking-[-0.04em]"
              >
                Find freight that fits the network.
              </h2>
              <p className="mt-5 max-w-2xl leading-7 text-muted-foreground">
                Research public and internal sources, rank return-lane opportunities, and review
                every claim before a simulated send.
              </p>
            </div>
            <ol className="grid gap-px bg-border sm:grid-cols-3">
              {["Research the shipper", "Score network fit", "Review the outreach"].map(
                (label, index) => (
                  <li key={label} className="bg-card p-5 text-sm">
                    <span className="mr-2 text-accent">0{index + 1}</span> {label}
                  </li>
                ),
              )}
            </ol>
          </section>
        ) : (
          <>
            <section
              className="rounded-3xl border border-border bg-card p-5 shadow-[0_20px_70px_rgb(22_28_25_/_7%)] sm:p-7"
              aria-labelledby="run-title"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold tracking-[0.16em] text-muted-foreground uppercase">
                    {run.account.name}
                  </p>
                  <h2 className="mt-2 text-xl font-semibold" id="run-title">
                    {run.stage}
                  </h2>
                </div>
                <span className="rounded-full bg-muted px-3 py-1 text-xs font-bold tracking-wide uppercase">
                  {run.status.replace("_", " ")}
                </span>
              </div>
              <div className="mt-5" role="status" aria-live="polite" aria-atomic="true">
                <div className="flex justify-between text-sm">
                  <span>{run.stage}</span>
                  <span>{run.progress_percent}%</span>
                </div>
                <progress
                  className="mt-2 h-2 w-full accent-accent"
                  max="100"
                  value={run.progress_percent}
                >
                  {run.progress_percent}%
                </progress>
              </div>
              <SourceCoverage sources={run.source_coverage} />
            </section>

            {actionError ? (
              <div
                role="alert"
                className="rounded-2xl border border-degraded/40 bg-degraded/10 p-4"
              >
                <p className="font-semibold">{actionError}</p>
                {isResearching ? (
                  <button
                    type="button"
                    onClick={() => setRun({ ...run })}
                    className="mt-2 text-sm font-bold text-accent underline underline-offset-4"
                  >
                    Retry progress update
                  </button>
                ) : null}
              </div>
            ) : null}

            {run.status === "failed" ? (
              <div
                role="alert"
                className="rounded-2xl border border-degraded/40 bg-degraded/10 p-5"
              >
                <h2 className="font-semibold">Research could not be completed</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  {run.error ?? "No customer-facing output was produced."}
                </p>
              </div>
            ) : null}

            <VerdictPanel run={run} />

            {run.status === "awaiting_review" && run.outreach && run.verdict === "fit" ? (
              <OutreachReview run={run} submitting={submitting} onReview={reviewRun} />
            ) : null}

            {run.status === "completed" && run.verdict === "fit" ? (
              <div role="status" className="rounded-2xl border border-ready/35 bg-ready/10 p-5">
                <p className="font-semibold text-ready">Simulated send recorded</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  No real email or CRM write occurred.
                </p>
              </div>
            ) : null}

            {run.status === "rejected" ? (
              <div role="status" className="rounded-2xl border border-border bg-card p-5">
                <p className="font-semibold">Draft rejected</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  The outreach was not sent. Your feedback was recorded.
                </p>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
