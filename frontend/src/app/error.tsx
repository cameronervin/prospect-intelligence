"use client";

import { alertStyle, buttonStyles, typeStyles } from "@/components/ui/styles";

export default function ErrorPage({ reset }: Readonly<{ reset: () => void }>) {
  return (
    <div className="max-w-xl px-4 py-6 sm:px-6 lg:px-8">
      <div role="alert" className={alertStyle}>
        <p className="font-semibold">The workspace couldn&apos;t be displayed</p>
        <p className={typeStyles.utility}>
          Error details are kept private. Nothing was sent. Try again.
        </p>
      </div>
      <button className={`${buttonStyles.secondary} mt-3`} type="button" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
