// Proxies browser requests under /api/* to the FastAPI backend, so the browser
// only ever talks to this origin. The target is read at request time (not at
// build time) so one image works in every environment.

import type { NextRequest } from "next/server";

import { apiBaseUrl } from "@/lib/api";
import { crossSite } from "@/lib/proxy";

const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "authorization", "cookie"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "cache-control"];
async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  if (crossSite(req)) {
    return Response.json({ detail: "Cross-site request refused." }, { status: 403 });
  }
  const { path } = await ctx.params;
  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, apiBaseUrl());
  target.search = req.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // Required by Node's fetch when streaming a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
      redirect: "manual",
    } as RequestInit);
  } catch {
    return Response.json({ detail: "The ScholarIQ API is not reachable." }, { status: 502 });
  }

  const out = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Each cookie must stay a separate header; joining them breaks Expires dates.
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const dynamic = "force-dynamic";
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
