export default function Loading() {
  return (
    <section
      className="rounded-2xl border border-border bg-card p-9"
      role="status"
      aria-busy="true"
    >
      <span className="sr-only">Checking application readiness</span>
      <div className="h-3 w-28 animate-pulse rounded bg-muted" aria-hidden="true" />
      <div className="mt-5 h-9 w-64 animate-pulse rounded bg-muted" aria-hidden="true" />
      <div className="mt-5 h-5 max-w-xl animate-pulse rounded bg-muted" aria-hidden="true" />
    </section>
  );
}
