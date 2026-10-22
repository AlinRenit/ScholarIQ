import { describe, expect, it } from "vitest";

import { crossSite } from "@/lib/proxy";

const req = (method: string, headers: Record<string, string>) =>
  new Request("http://app.test/api/profile", { method, headers });

describe("crossSite", () => {
  it("allows reads and same-origin writes", () => {
    expect(crossSite(req("GET", { origin: "https://evil.test", host: "app.test" }))).toBe(false);
    expect(crossSite(req("POST", { origin: "http://app.test", host: "app.test" }))).toBe(false);
    expect(crossSite(req("POST", { host: "app.test" }))).toBe(false);
  });

  it("refuses writes from another site", () => {
    expect(crossSite(req("POST", { origin: "https://evil.test", host: "app.test" }))).toBe(true);
    expect(crossSite(req("DELETE", { origin: "null", host: "app.test" }))).toBe(true);
    expect(crossSite(req("PUT", { "sec-fetch-site": "cross-site", host: "app.test" }))).toBe(true);
  });
});
