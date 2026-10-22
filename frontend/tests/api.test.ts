import { describe, expect, it } from "vitest";

import { ApiError, api, load } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("api client", () => {
  it("returns readiness details even when the API reports 503", async () => {
    const body = { status: "failed", checks: [] };
    await expect(api.readiness(() => json(body, 503))).resolves.toEqual(body);
  });

  it("raises ApiError for other failures", async () => {
    await expect(api.systemInfo(() => json({}, 500))).rejects.toBeInstanceOf(ApiError);
  });

  it("reports an unreachable API without throwing from load()", async () => {
    const result = await load(() => api.systemInfo(() => Promise.reject(new TypeError("x"))));
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not reachable/);
  });
});
