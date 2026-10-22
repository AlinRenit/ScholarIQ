import "server-only";

import { cookies } from "next/headers";

import { apiBaseUrl } from "@/lib/api";

export type ServerResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; message: string };

/** GET from the backend on behalf of the current visitor (forwards their cookie). */
export async function serverGet<T>(path: string): Promise<ServerResult<T>> {
  const cookieHeader = (await cookies()).toString();
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl()}${path}`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: null, message: "The ScholarIQ API is not reachable." };
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body ? String(body.detail) : res.statusText;
    return { ok: false, status: res.status, message: detail };
  }
  return { ok: true, data: (await res.json()) as T };
}
