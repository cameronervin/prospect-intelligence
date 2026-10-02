import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendBaseUrl } from "@/server/env";
import { SESSION_COOKIE } from "@/features/auth/constants";
import { correlationId, serverLog } from "@/server/logging";

type RouteContext = { params: Promise<{ path: string[] }> };

const API_PREFIX = "/api/v1/";

function errorEnvelope(
  status: number,
  code: "not_found" | "validation_error" | "service_unavailable",
  message: string,
  requestId: string,
) {
  return NextResponse.json(
    { error: { code, message, retryable: status === 503, issues: [] } },
    { status, headers: { "x-correlation-id": requestId } },
  );
}

async function proxy(request: NextRequest, context: RouteContext) {
  const requestId = correlationId(request.headers.get("x-correlation-id"));
  const { path } = await context.params;
  // Dot segments would let the resolved URL escape the backend's /api/v1 surface.
  if (path.some((segment) => segment === "." || segment === "..")) {
    serverLog("warning", "backend_proxy_path_rejected", {
      correlation_id: requestId,
      reason: "dot_segment",
    });
    return errorEnvelope(400, "validation_error", "The request path is not valid.", requestId);
  }
  const allowed =
    (path.length === 1 && (path[0] === "accounts" || path[0] === "prospect-runs")) ||
    (path.length === 2 && path[0] === "prospect-runs") ||
    (path.length === 3 && path[0] === "prospect-runs" && path[2] === "review");
  if (!allowed) {
    serverLog("warning", "backend_proxy_path_rejected", {
      correlation_id: requestId,
      reason: "route_not_allowed",
    });
    return errorEnvelope(404, "not_found", "The requested API route was not found.", requestId);
  }
  const safePath = path.map(encodeURIComponent).join("/");
  const url = new URL(`${API_PREFIX}${safePath}${request.nextUrl.search}`, backendBaseUrl());
  if (!url.pathname.startsWith(API_PREFIX)) {
    serverLog("warning", "backend_proxy_path_rejected", {
      correlation_id: requestId,
      reason: "prefix_escape",
    });
    return errorEnvelope(400, "validation_error", "The request path is not valid.", requestId);
  }
  const headers = new Headers();
  for (const name of ["content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);
  headers.set("x-correlation-id", requestId);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
    const proxied = new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "x-correlation-id": requestId,
      },
    });
    if (response.status === 401) proxied.cookies.delete(SESSION_COOKIE);
    return proxied;
  } catch (caught) {
    serverLog("error", "backend_proxy_failed", {
      correlation_id: requestId,
      operation: "prospect_api",
      error_type: caught instanceof Error ? caught.name : "UnknownError",
    });
    return errorEnvelope(
      503,
      "service_unavailable",
      "The prospect service is temporarily unavailable.",
      requestId,
    );
  }
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
