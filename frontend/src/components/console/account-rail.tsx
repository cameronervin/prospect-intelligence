import { useId } from "react";

import { alertStyle, buttonStyles, linkButton, typeStyles } from "@/components/ui/styles";
import type { Account } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

export type AccountsState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; accounts: Account[] };

export function AccountRail({
  state,
  selectedId,
  locked,
  starting,
  running = false,
  startError,
  quiet = false,
  onSelect,
  onStart,
  onRetry,
  onReload,
}: Readonly<{
  state: AccountsState;
  selectedId?: string;
  locked: boolean;
  starting: boolean;
  /** The agent is working on the selected account. */
  running?: boolean;
  startError: boolean;
  /** A brief is on screen, so building another is a secondary action. */
  quiet?: boolean;
  onSelect: (account: Account) => void;
  onStart: () => void;
  onRetry: () => void;
  onReload: () => void;
}>) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col border-b border-slate-200 bg-slate-50 lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0"
    >
      <div className="flex items-center justify-between gap-2 px-4 pt-2">
        <h2 id={headingId} className={typeStyles.section}>
          Accounts
        </h2>
        <button
          type="button"
          className={linkButton}
          aria-label="Reload accounts"
          disabled={state.kind === "loading" || locked}
          onClick={onReload}
        >
          Reload
        </button>
      </div>
      {state.kind === "ready" ? (
        <p className={`${typeStyles.utility} px-4 pb-2`}>{`${state.accounts.length} assigned`}</p>
      ) : null}

      {state.kind === "loading" ? (
        <p role="status" className={`${typeStyles.utility} px-4 py-2`}>
          Loading accounts…
        </p>
      ) : null}

      {state.kind === "error" ? (
        <div className="px-4 pb-2">
          <div role="alert" className={alertStyle}>
            <p className="font-semibold">We couldn&apos;t load your accounts</p>
            <p className={typeStyles.utility}>It&apos;s safe to try again.</p>
          </div>
          <button type="button" className={`${buttonStyles.secondary} mt-3`} onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}

      {state.kind === "ready" && state.accounts.length === 0 ? (
        <p className={`${typeStyles.utility} px-4 py-2`}>No accounts are assigned to you.</p>
      ) : null}

      {state.kind === "ready" && state.accounts.length > 0 ? (
        <ul className="flex flex-col gap-0.5 px-2">
          {state.accounts.map((account) => {
            const selected = account.id === selectedId;
            return (
              <li key={account.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  disabled={locked}
                  onClick={() => onSelect(account)}
                  className={cn(
                    "flex min-h-11 w-full flex-col gap-0.5 rounded border px-2.5 py-2 text-left transition-colors motion-reduce:transition-none disabled:cursor-not-allowed",
                    selected ? "border-slate-300 bg-white" : "border-transparent hover:bg-white",
                  )}
                >
                  <span className={cn("text-sm", selected ? "font-semibold" : "font-medium")}>
                    {account.name}
                  </span>
                  <span className={typeStyles.utility}>
                    {account.relationship}
                    {account.location ? ` · ${account.location}` : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      <div className="p-4">
        <button
          type="button"
          className={cn(quiet ? buttonStyles.secondary : buttonStyles.primary, "w-full")}
          disabled={!selectedId || locked || starting}
          onClick={onStart}
        >
          {starting ? "Starting…" : running ? "Agent running…" : "Run prospect agent"}
        </button>
        {startError ? (
          <div role="alert" className={`${alertStyle} mt-3`}>
            <p className="font-semibold">The agent run couldn&apos;t be started</p>
            <p className={typeStyles.utility}>Your account selection is kept. Try again.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
