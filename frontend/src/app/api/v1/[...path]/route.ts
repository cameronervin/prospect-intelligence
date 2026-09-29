import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendBaseUrl } from "@/server/env";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const safePath = path.map(encodeURIComponent).join("/");
  const url = new URL(`/api/v1/${safePath}${request.nextUrl.search}`, backendBaseUrl());
  const headers = new Headers();
  for (const name of ["content-type", "x-tenant-id", "x-rep-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
