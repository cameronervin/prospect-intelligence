import { ProspectWorkspace } from "@/components/prospect-workspace";

export default function HomePage() {
  return (
    <div className="grid gap-[clamp(2.5rem,6vw,4.5rem)]">
      <section className="max-w-5xl" aria-labelledby="page-title">
        <p className="text-xs font-bold tracking-[0.16em] text-accent uppercase">
          Freight prospect intelligence
        </p>
        <h1
          className="mt-5 max-w-[15ch] text-[clamp(3rem,8vw,6.5rem)] leading-[0.94] font-semibold tracking-[-0.055em]"
          id="page-title"
        >
          Turn empty miles into qualified conversations.
        </h1>
        <p className="mt-7 max-w-2xl text-[clamp(1.05rem,2vw,1.3rem)] leading-8 text-muted-foreground">
          Build an evidence-backed shipper brief, find lanes that fit your network, and keep a rep
          in control of every customer-facing message.
        </p>
      </section>
      <ProspectWorkspace />
    </div>
  );
}
