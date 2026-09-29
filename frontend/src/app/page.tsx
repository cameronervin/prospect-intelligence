import { StatusPanel } from "@/components/status-panel";
import { getBackendHealth } from "@/server/backend-health";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const health = await getBackendHealth();
  return (
    <div className="grid gap-[clamp(2.5rem,6vw,5rem)]">
      <section className="max-w-4xl" aria-labelledby="page-title">
        <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">
          Enterprise agent foundation
        </p>
        <h1
          className="mt-5 max-w-[14ch] text-[clamp(3rem,8vw,6.5rem)] leading-[0.94] font-semibold tracking-[-0.055em]"
          id="page-title"
        >
          Ready for a real problem.
        </h1>
        <p className="mt-7 max-w-2xl text-[clamp(1.05rem,2vw,1.3rem)] leading-8 text-muted-foreground">
          The application, persistence, evaluation, and delivery boundaries are in place. Product
          behavior begins only after the domain and success metric are selected.
        </p>
      </section>
      <StatusPanel health={health} />
    </div>
  );
}
