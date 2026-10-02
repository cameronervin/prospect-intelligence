import { redirect } from "next/navigation";

import { BrandMark } from "@/components/brand-mark";
import { typeStyles } from "@/components/ui/styles";
import { LoginForm } from "@/features/auth/login-form";
import { currentSession } from "@/server/auth-session";

export default async function LoginPage() {
  if (await currentSession()) redirect("/");
  return (
    <main className="grid min-h-dvh bg-slate-100 px-4 py-10 sm:place-items-center">
      <section className="w-full max-w-md border border-slate-300 bg-white">
        <header className="flex items-center gap-2 border-b border-slate-200 px-5 py-3">
          <BrandMark />
          <span className={typeStyles.wordmark}>Prospect Intelligence</span>
        </header>
        <div className="px-5 py-7 sm:px-8">
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            Sign in to the dispatch console
          </h1>
          <LoginForm />
          <div className="mt-7 border-t border-slate-200 pt-4 text-xs leading-5 text-slate-500">
            Demo password: <code className="font-mono text-slate-700">prospect-demo</code>
          </div>
        </div>
      </section>
    </main>
  );
}
