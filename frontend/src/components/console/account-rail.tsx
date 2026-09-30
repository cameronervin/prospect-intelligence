import { useEffect, useId, useRef } from "react";

import { AccountRailLoading } from "@/components/ui/loading-skeleton";
import { alertStyle, buttonStyles, linkButton, typeStyles } from "@/components/ui/styles";
import type { Account } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

export type AccountsState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; accounts: Account[] };

export const ACCOUNT_PAGE_SIZE = 5;

export function AccountRail({
  state,
  page,
  selectedId,
  locked,
  starting,
  running = false,
  startError,
  quiet = false,
  onSelect,
  onPageChange,
  onStart,
  onRetry,
  onReload,
}: Readonly<{
  state: AccountsState;
  page: number;
  selectedId?: string;
  locked: boolean;
  starting: boolean;
  /** The agent is working on the selected account. */
  running?: boolean;
  startError: boolean;
  /** A brief is on screen, so building another is a secondary action. */
  quiet?: boolean;
  onSelect: (account: Account) => void;
  onPageChange: (page: number) => void;
  onStart: () => void;
  onRetry: () => void;
  onReload: () => void;
}>) {
  const headingId = useId();
  const firstVisibleAccountRef = useRef<HTMLButtonElement>(null);
  const focusPageRef = useRef<number | undefined>(undefined);
  const totalAccounts = state.kind === "ready" ? state.accounts.length : 0;
  const totalPages = Math.max(1, Math.ceil(totalAccounts / ACCOUNT_PAGE_SIZE));
  const visiblePage = Math.min(Math.max(page, 1), totalPages);
  const firstVisible = (visiblePage - 1) * ACCOUNT_PAGE_SIZE;
  const visibleAccounts =
    state.kind === "ready"
      ? state.accounts.slice(firstVisible, firstVisible + ACCOUNT_PAGE_SIZE)
      : [];
  const selectionIsCurrent =
    state.kind === "ready" && state.accounts.some((account) => account.id === selectedId);

  useEffect(() => {
    if (focusPageRef.current !== visiblePage) return;
    firstVisibleAccountRef.current?.focus();
    focusPageRef.current = undefined;
  }, [visiblePage]);

  function changePage(nextPage: number) {
    focusPageRef.current = nextPage;
    onPageChange(nextPage);
  }

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
        <p className={`${typeStyles.utility} px-4 pb-2 tabular-nums`}>
          {totalAccounts > ACCOUNT_PAGE_SIZE
            ? `${firstVisible + 1}–${Math.min(firstVisible + ACCOUNT_PAGE_SIZE, totalAccounts)} of ${totalAccounts} assigned`
            : `${totalAccounts} assigned`}
        </p>
      ) : null}

      {state.kind === "loading" ? <AccountRailLoading /> : null}

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
          {visibleAccounts.map((account, index) => {
            const selected = account.id === selectedId;
            return (
              <li key={account.id}>
                <button
                  ref={index === 0 ? firstVisibleAccountRef : undefined}
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

      {state.kind === "ready" && totalAccounts > ACCOUNT_PAGE_SIZE ? (
        <nav
          aria-label="Account pages"
          className="flex items-center justify-between gap-2 px-4 pt-2"
        >
          <button
            type="button"
            className={linkButton}
            disabled={locked || visiblePage === 1}
            onClick={() => changePage(visiblePage - 1)}
          >
            Previous
          </button>
          <span
            aria-atomic="true"
            aria-live="polite"
            className={`${typeStyles.utility} tabular-nums`}
          >{`Page ${visiblePage} of ${totalPages}`}</span>
          <button
            type="button"
            className={linkButton}
            disabled={locked || visiblePage === totalPages}
            onClick={() => changePage(visiblePage + 1)}
          >
            Next
          </button>
        </nav>
      ) : null}

      <div className="p-4">
        <button
          type="button"
          className={cn(quiet ? buttonStyles.secondary : buttonStyles.primary, "w-full")}
          disabled={!selectionIsCurrent || locked || starting}
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
