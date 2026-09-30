import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendBaseUrl } from "@/server/env";

type RouteContext = { params: Promise<{ path: string[] }> };

const API_PREFIX = "/api/v1/";

function errorEnvelope(
  status: number,
  code: "validation_error" | "service_unavailable",
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
  const safePath = path.map(encodeURIComponent).join("/");
  const url = new URL(`${API_PREFIX}${safePath}${request.nextUrl.search}`, backendBaseUrl());
  if (!url.pathname.startsWith(API_PREFIX)) {
    return errorEnvelope(400, "validation_error", "The request path is not valid.");
  }
  const headers = new Headers();
  for (const name of ["content-type", "x-tenant-id", "x-rep-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
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
