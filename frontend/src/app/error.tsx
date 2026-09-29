"use client";

export default function ErrorPage({ reset }: Readonly<{ reset: () => void }>) {
  return (
    <section className="max-w-2xl rounded-2xl border border-border bg-card p-9" role="alert">
      <h1 className="text-3xl font-semibold">The application shell could not render.</h1>
      <p className="mt-4 leading-7 text-muted-foreground">
        Private error details were not displayed. Try the request again.
      </p>
      <button
        className="mt-6 rounded-lg bg-foreground px-4 py-2 font-semibold text-background focus-visible:outline-2 focus-visible:outline-offset-2"
        type="button"
        onClick={reset}
      >
        Try again
      </button>
    </section>
  );
}
