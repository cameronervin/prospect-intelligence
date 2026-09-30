"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AccountRail, type AccountsState } from "@/components/console/account-rail";
import { isActive } from "@/components/console/format";
import { alertStyle, buttonStyles, typeStyles } from "@/components/ui/styles";
import { RunView } from "@/features/prospect-intelligence/components/run-view";
import { useRunRestoration } from "@/features/prospect-intelligence/hooks/use-run-restoration";
import { rememberRun } from "@/features/prospect-intelligence/run/active-run-storage";
import {
  ACTIVE_RUN_STORAGE_KEY,
  MAX_POLL_RETRIES,
} from "@/features/prospect-intelligence/run/constants";
import { DEMO_REP_ID, DEMO_TENANT_ID } from "@/lib/demo-identity";
import {
  createProspectClient,
  type Account,
  type ProspectClient,
  type ProspectRun,
  type RunReview,
} from "@/lib/prospect-api";

export { ACTIVE_RUN_STORAGE_KEY };

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

  const show = useCallback((next: ProspectRun | undefined) => {
    currentRunId.current = next?.id;
    rememberRun(next);
    setRun(next);
  }, []);

  const { restoring, restoreFailed, retryRestore } = useRunRestoration({
    accounts,
    api,
    show,
    selectAccount: setSelected,
  });

  useEffect(() => {
    if (!run || !isActive(run.status) || pollPaused) return;
    let cancelled = false;
    const timer = setTimeout(
      async () => {
        try {
          const next = await api.getRun(run.id);
          if (cancelled) return;
          setPollFailures(0);
          show(next);
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
  }, [api, run, pollFailures, pollPaused, pollIntervalMs, show]);

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
      show(next);
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
    show(next);
  }

  const locked =
    starting ||
    deciding ||
    restoring ||
    restoreFailed ||
    Boolean(run && (isActive(run.status) || run.status === "awaiting_review"));

  return (
    <div className="flex w-full flex-1 flex-col lg:flex-row">
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

      <section aria-label="Workspace" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-6xl">
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
          ) : restoreFailed ? (
            <div role="alert" className={`${alertStyle} max-w-xl`}>
              <p className="font-semibold">Your active run could not be restored</p>
              <p className={typeStyles.utility}>
                Account switching and new runs remain locked so a pending review is not orphaned.
              </p>
              <div className="mt-1.5">
                <button
                  type="button"
                  className={buttonStyles.secondary}
                  onClick={() => {
                    retryRestore();
                    if (accounts.kind === "error") reloadAccounts();
                  }}
                >
                  Retry restoring run
                </button>
              </div>
            </div>
          ) : (
            <div className="max-w-xl rounded border border-dashed border-slate-300 px-4 py-5">
              <p className="text-sm font-semibold">Select an account to run the prospect agent</p>
              <p className={`${typeStyles.utility} mt-1`}>
                Agents research the account, score lanes against your network, draft outreach, and
                check its quality. You watch each attempt here and review the message before
                anything is sent.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
