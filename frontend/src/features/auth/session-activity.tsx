"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";

const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

export function SessionActivity() {
  const router = useRouter();
  useEffect(() => {
    // The cookie may already be close to its one-hour expiry after a reload. Refresh on the
    // first qualifying interaction, then throttle subsequent activity.
    let lastRefresh = 0;
    let refreshing = false;
    async function refresh() {
      if (document.visibilityState !== "visible" || refreshing) return;
      if (Date.now() - lastRefresh < REFRESH_INTERVAL_MS) return;
      refreshing = true;
      lastRefresh = Date.now();
      try {
        const response = await fetch("/api/auth/refresh", { method: "POST" });
        if (response.status === 401) {
          router.replace("/login" as Route);
          router.refresh();
          return;
        }
      } catch {
        // A transient network failure keeps the existing cookie and remains activity-throttled.
      } finally {
        refreshing = false;
      }
    }
    const events: (keyof WindowEventMap)[] = ["focus", "keydown", "pointerdown"];
    for (const event of events) window.addEventListener(event, refresh, { passive: true });
    return () => {
      for (const event of events) window.removeEventListener(event, refresh);
    };
  }, [router]);
  return null;
}
