import { useEffect, useState } from "react";

import { ProspectApiError, type ProspectClient } from "../api/client";
import type { Account, ProspectRun } from "../api/schemas";
import { rememberRun, storedRunId } from "../run/active-run-storage";

type AccountsState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; accounts: Account[] };

function shouldRestore(run: ProspectRun) {
  return run.status === "queued" || run.status === "running" || run.status === "awaiting_review";
}

type Options = {
  accounts: AccountsState;
  api: ProspectClient;
  show: (run: ProspectRun | undefined) => void;
  selectAccount: (account: Account) => void;
  subject?: string;
};

/** Restore the tab's durable active run before account or new-run navigation can unlock. */
export function useRunRestoration({
  accounts,
  api,
  show,
  selectAccount,
  subject = "test-user",
}: Options) {
  const [restoring, setRestoring] = useState(() => Boolean(storedRunId(subject)));
  const [restoreFailed, setRestoreFailed] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);

  useEffect(() => {
    if (accounts.kind === "loading") return;
    let cancelled = false;
    void Promise.resolve().then(async () => {
      const runId = storedRunId(subject);
      if (!runId) {
        if (!cancelled) {
          setRestoring(false);
          setRestoreFailed(false);
        }
        return;
      }
      if (accounts.kind !== "ready") {
        if (!cancelled) {
          setRestoring(false);
          setRestoreFailed(true);
        }
        return;
      }
      setRestoring(true);
      setRestoreFailed(false);
      try {
        const next = await api.getRun(runId);
        if (cancelled) return;
        if (!shouldRestore(next)) {
          rememberRun(subject, undefined);
          setRestoring(false);
          return;
        }
        const account = accounts.accounts.find((item) => item.id === next.account.id);
        if (!account) throw new Error("active run account is not visible");
        selectAccount(account);
        show(next);
        setRestoring(false);
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ProspectApiError && error.code === "not_found") {
          rememberRun(subject, undefined);
          setRestoring(false);
          setRestoreFailed(false);
          return;
        }
        setRestoring(false);
        setRestoreFailed(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [accounts, api, restoreAttempt, selectAccount, show, subject]);

  function retryRestore() {
    setRestoreFailed(false);
    setRestoring(true);
    setRestoreAttempt((attempt) => attempt + 1);
  }

  return { restoring, restoreFailed, retryRestore };
}
