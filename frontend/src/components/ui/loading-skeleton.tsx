import { typeStyles } from "@/components/ui/styles";

const pulse = "motion-safe:animate-pulse";

function AccountRows() {
  return (
    <ul aria-hidden="true" className="flex flex-col gap-0.5 px-2">
      {Array.from({ length: 5 }, (_, index) => (
        <li
          key={index}
          aria-hidden="true"
          data-skeleton="account-row"
          className={`${pulse} flex min-h-14 flex-col justify-center gap-1.5 rounded border border-transparent px-2.5 py-2`}
        >
          <span className="h-3 w-2/3 rounded bg-slate-200" />
          <span className="h-2 w-1/2 rounded bg-slate-200" />
        </li>
      ))}
    </ul>
  );
}

export function AccountRailLoading() {
  return (
    <>
      <p role="status" className={`${typeStyles.utility} px-4 pb-2`}>
        Loading accounts…
      </p>
      <AccountRows />
    </>
  );
}

export function WorkspaceLoading() {
  return (
    <div>
      <p role="status" aria-label="Workspace loading status" className={typeStyles.utility}>
        Loading workspace…
      </p>
      <div
        aria-hidden="true"
        data-skeleton="workspace"
        className={`${pulse} mt-3 max-w-xl rounded border border-slate-200 px-4 py-5`}
      >
        <div className="h-4 w-2/3 rounded bg-slate-200" />
        <div className="mt-3 h-3 w-full rounded bg-slate-100" />
        <div className="mt-2 h-3 w-4/5 rounded bg-slate-100" />
      </div>
    </div>
  );
}

export function RunLoading({ message }: Readonly<{ message: string }>) {
  return (
    <div>
      <p role="status" aria-label="Run loading status" className={typeStyles.utility}>
        {message}
      </p>
      <div aria-hidden="true" data-skeleton="run" className={`${pulse} mt-3`}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
          <div className="flex-1">
            <div className="h-3 w-24 rounded bg-slate-200" />
            <div className="mt-2 h-6 w-2/3 rounded bg-slate-200" />
          </div>
          <div className="h-7 w-24 rounded-full bg-slate-200" />
        </div>
        <div className="mt-7 rounded border border-slate-300 px-4 pt-3 pb-1 sm:px-6">
          <div className="flex items-center justify-between gap-4 pb-1">
            <div className="h-5 w-36 rounded bg-slate-200" />
            <div className="h-3 w-64 rounded bg-slate-100" />
          </div>
          <ol>
            {Array.from({ length: 6 }, (_, index) => (
              <li
                key={index}
                className="flex items-center gap-3 border-b border-slate-200 py-3 last:border-b-0"
              >
                <span className="size-6 shrink-0 rounded-full bg-slate-200" />
                <span className="h-3 flex-1 rounded bg-slate-100" />
                <span className="h-6 w-16 rounded-full bg-slate-200" />
                <span className="h-3 w-12 rounded bg-slate-100" />
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

export function ConsoleLoading() {
  return (
    <div className="flex w-full flex-1 flex-col lg:flex-row">
      <section
        aria-label="Accounts"
        className="flex flex-col border-b border-slate-200 bg-slate-50 lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0"
      >
        <div className="px-4 pt-4 pb-2">
          <h2 className={typeStyles.section}>Accounts</h2>
        </div>
        <AccountRailLoading />
      </section>
      <section aria-label="Workspace" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-6xl">
          <WorkspaceLoading />
        </div>
      </section>
    </div>
  );
}
