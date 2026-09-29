import type { BackendHealth } from "@/server/backend-health";

export function StatusPanel({ health }: Readonly<{ health: BackendHealth }>) {
  const ready = health.kind === "ready";
  return (
    <section
      className="rounded-2xl border border-border bg-card p-7 shadow-[0_24px_70px_rgb(22_28_25_/_8%)] sm:p-9"
      aria-labelledby="status-title"
      role="status"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-bold tracking-[0.16em] text-muted-foreground uppercase">
            System status
          </p>
          <h2 className="mt-2 text-2xl font-semibold" id="status-title">
            {ready ? "Foundation ready" : "Backend unavailable"}
          </h2>
        </div>
        <span
          className={
            ready
              ? "rounded-full bg-ready/10 px-3 py-1 text-sm font-semibold text-ready"
              : "rounded-full bg-degraded/10 px-3 py-1 text-sm font-semibold text-degraded"
          }
        >
          {ready ? "Ready" : "Degraded"}
        </span>
      </div>
      <p className="mt-5 max-w-2xl leading-7 text-muted-foreground">
        {ready
          ? "The application shell can reach the backend and its PostgreSQL dependency."
          : "The interface remains available, but the backend readiness check did not complete successfully."}
      </p>
      <p className="mt-5 text-xs text-muted-foreground">
        Checked <time dateTime={health.checkedAt}>{health.checkedAt}</time>
      </p>
    </section>
  );
}
