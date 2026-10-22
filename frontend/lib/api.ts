// Typed client for the ScholarIQ backend. Server components call the backend
// directly; browser code goes through the /api rewrite in next.config.ts.

export type CheckStatus = "ok" | "degraded" | "failed";

export type HealthCheck = {
  name: string;
  status: CheckStatus;
  detail: string;
  required: boolean;
};

export type Readiness = { status: CheckStatus; checks: HealthCheck[] };

export type Capability = {
  key: string;
  label: string;
  milestone: number;
  status: "available" | "planned";
};

export type SystemInfo = {
  name: string;
  version: string;
  deployment_mode: "server" | "offline";
  intelligence: string;
  uses_external_ai: boolean;
  capabilities: Capability[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiBaseUrl(): string {
  if (typeof window !== "undefined") return "";
  return process.env.SCHOLARIQ_API_URL ?? "http://localhost:8000";
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export async function getJson<T>(
  path: string,
  opts: { fetchImpl?: FetchLike; acceptStatuses?: number[] } = {},
): Promise<T> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  let res: Response;
  try {
    res = await fetchImpl(`${apiBaseUrl()}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError("The ScholarIQ API is not reachable.", null);
  }
  if (!res.ok && !(opts.acceptStatuses ?? []).includes(res.status)) {
    throw new ApiError(`Request to ${path} failed with status ${res.status}.`, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  systemInfo: (fetchImpl?: FetchLike) => getJson<SystemInfo>("/api/system/info", { fetchImpl }),
  // 503 still carries the per-check breakdown, which is what we want to show.
  readiness: (fetchImpl?: FetchLike) =>
    getJson<Readiness>("/api/health/ready", { fetchImpl, acceptStatuses: [503] }),
};

/** Load data for a server component, returning an error message instead of throwing. */
export async function load<T>(
  fn: () => Promise<T>,
): Promise<{ data: T; error: null } | { data: null; error: string }> {
  try {
    return { data: await fn(), error: null };
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : "Unknown error" };
  }
}
