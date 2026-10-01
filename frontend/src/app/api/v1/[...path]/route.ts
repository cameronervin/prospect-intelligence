import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendBaseUrl } from "@/server/env";
import { SESSION_COOKIE } from "@/features/auth/constants";

type RouteContext = { params: Promise<{ path: string[] }> };

const API_PREFIX = "/api/v1/";

function errorEnvelope(
  status: number,
  code: "not_found" | "validation_error" | "service_unavailable",
  message: string,
) {
  return NextResponse.json(
    { error: { code, message, retryable: status === 503, issues: [] } },
    { status },
  );
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  // Dot segments would let the resolved URL escape the backend's /api/v1 surface.
  if (path.some((segment) => segment === "." || segment === "..")) {
    return errorEnvelope(400, "validation_error", "The request path is not valid.");
  }
  const allowed =
    (path.length === 1 && (path[0] === "accounts" || path[0] === "prospect-runs")) ||
    (path.length === 2 && path[0] === "prospect-runs") ||
    (path.length === 3 && path[0] === "prospect-runs" && path[2] === "review");
  if (!allowed) {
    return errorEnvelope(404, "not_found", "The requested API route was not found.");
  }
  const safePath = path.map(encodeURIComponent).join("/");
  const url = new URL(`${API_PREFIX}${safePath}${request.nextUrl.search}`, backendBaseUrl());
  if (!url.pathname.startsWith(API_PREFIX)) {
    return errorEnvelope(400, "validation_error", "The request path is not valid.");
  }
  const headers = new Headers();
  for (const name of ["content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);
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
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
    if (response.status === 401) proxied.cookies.delete(SESSION_COOKIE);
    return proxied;
  } catch {
    return errorEnvelope(
      503,
      "service_unavailable",
      "The prospect service is temporarily unavailable.",
    );
  }
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
