import { z } from "zod";

import { backendBaseUrl } from "@/server/env";

const ReadyResponse = z.object({ status: z.literal("ready") });

export type BackendHealth =
  { kind: "ready"; checkedAt: string } | { kind: "degraded"; checkedAt: string };

export type HealthFetch = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export async function getBackendHealth(
  fetcher: HealthFetch = fetch,
  timeoutMs = 2_000,
  now: () => Date = () => new Date(),
): Promise<BackendHealth> {
  const checkedAt = now().toISOString();
  try {
    const response = await fetcher(new URL("/health/ready", backendBaseUrl()), {
      cache: "no-store",
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      return { kind: "degraded", checkedAt };
    }
    ReadyResponse.parse(await response.json());
    return { kind: "ready", checkedAt };
  } catch {
    return { kind: "degraded", checkedAt };
  }
}
