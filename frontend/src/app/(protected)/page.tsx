import type { Route } from "next";
import { redirect } from "next/navigation";

import { BrandMark } from "@/components/brand-mark";
import { ProspectWorkspace } from "@/components/prospect-workspace";
import { typeStyles } from "@/components/ui/styles";
import { SessionActivity } from "@/features/auth/session-activity";
import { SignOut } from "@/features/auth/sign-out";
import { currentSession } from "@/server/auth-session";

export default async function HomePage() {
  const user = await currentSession();
  if (!user) redirect("/login" as Route);
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-slate-200 px-4 sm:px-5">
        <div className="flex items-center gap-2">
          <BrandMark />
          <h1 className={typeStyles.wordmark}>Prospect Intelligence</h1>
        </div>
        <div className="flex items-center gap-3">
          <p className={typeStyles.utility}>{user.display_name} · Sales rep</p>
          <SignOut subject={user.subject} />
        </div>
      </header>
      <main className="flex flex-1">
        <ProspectWorkspace subject={user.subject} />
      </main>
      <SessionActivity />
    </div>
  );
}
