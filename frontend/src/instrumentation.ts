import type { Instrumentation } from "next";

import { serverLog } from "@/server/logging";

export function register() {
  if (process.env.NEXT_RUNTIME !== "edge") {
    serverLog("info", "frontend_started", { runtime: process.env.NEXT_RUNTIME ?? "nodejs" });
  }
}

export const onRequestError: Instrumentation.onRequestError = (error, request, context) => {
  const errorType = error instanceof Error ? error.name : "UnknownError";
  const errorDigest =
    typeof error === "object" && error !== null && "digest" in error
      ? String(error.digest)
      : undefined;
  serverLog("error", "frontend_request_error", {
    error_type: errorType,
    error_digest: errorDigest,
    method: request.method,
    route: context.routePath,
    route_type: context.routeType,
    router_kind: context.routerKind,
  });
};
