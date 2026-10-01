"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";

import { clearRememberedRun } from "@/features/prospect-intelligence/run/active-run-storage";

export function SignOut({ subject }: Readonly<{ subject: string }>) {
  const router = useRouter();
  return (
    <button
      type="button"
      className="text-xs font-semibold text-slate-600 underline-offset-4 hover:text-slate-950 hover:underline"
      onClick={async () => {
        try {
          await fetch("/api/auth/logout", { method: "POST" });
        } finally {
          clearRememberedRun(subject);
          router.replace("/login" as Route);
          router.refresh();
        }
      }}
    >
      Sign out
    </button>
  );
}
