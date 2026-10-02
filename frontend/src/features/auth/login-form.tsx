"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { buttonStyles, fieldLabel } from "@/components/ui/styles";

export function LoginForm() {
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<"credentials" | "unavailable">();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      if (!response.ok) {
        setError(response.status === 401 ? "credentials" : "unavailable");
        requestAnimationFrame(() => emailRef.current?.focus());
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setError("unavailable");
      requestAnimationFrame(() => emailRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-7 space-y-5"
      aria-describedby={error ? "login-error" : undefined}
    >
      <div className="space-y-1.5">
        <label htmlFor="email" className={fieldLabel}>
          Email
        </label>
        <input
          ref={emailRef}
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          defaultValue="alex.morgan@example.test"
          required
          disabled={busy}
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-950 focus:ring-2 focus:ring-orange-200 disabled:bg-slate-100"
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="password" className={fieldLabel}>
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          disabled={busy}
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-950 focus:ring-2 focus:ring-orange-200 disabled:bg-slate-100"
        />
      </div>
      {error ? (
        <p
          id="login-error"
          role="alert"
          className="border-l-2 border-red-600 pl-3 text-sm text-slate-700"
        >
          {error === "credentials"
            ? "Email or password is incorrect."
            : "The sign-in service is temporarily unavailable. Try again."}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={busy}
        aria-busy={busy}
        className={`${buttonStyles.primary} w-full justify-center bg-orange-600 hover:bg-orange-700`}
      >
        {busy ? "Checking access…" : "Enter"}
      </button>
    </form>
  );
}
