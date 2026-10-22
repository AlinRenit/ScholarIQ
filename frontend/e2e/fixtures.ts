import fs from "node:fs";
import path from "node:path";

import {
  test as base,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from "@playwright/test";

const LOCAL = /^(https?|wss?):\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?\//;

/**
 * The browser side of the offline check: any request a page in this context
 * makes to a host other than this machine is aborted and recorded. The
 * returned list is checked when the test (or a serial group) ends.
 */
export async function blockOutbound(context: BrowserContext): Promise<string[]> {
  const outbound: string[] = [];
  await context.route("**/*", (route) => {
    const url = route.request().url();
    if (LOCAL.test(url) || url.startsWith("data:") || url.startsWith("blob:")) {
      return route.continue();
    }
    outbound.push(url);
    return route.abort("internetdisconnected");
  });
  return outbound;
}

export const test = base.extend<{ noOutbound: void }>({
  noOutbound: [
    async ({ context }, use) => {
      const outbound = await blockOutbound(context);
      await use();
      expect(outbound, "requests to hosts other than this machine").toEqual([]);
    },
    { scope: "test", auto: true },
  ],
});

export { expect };

export const MARKSHEET = path.resolve(
  __dirname,
  "../../backend/tests/fixtures/marksheets/digital_semester3.pdf",
);

export async function createProfile(page: Page, name = "E2E Student"): Promise<void> {
  await page.goto("/academics");
  await page.getByLabel("Name to show").fill(name);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create profile" }).click();
  await expect(page.getByRole("heading", { name: "Import a marksheet" })).toBeVisible();
}

/** Upload the sample marksheet and save its results as extracted (API, for setup only). */
export async function importMarksheet(request: APIRequestContext): Promise<void> {
  const up = await request.post("/api/documents", {
    multipart: {
      file: {
        name: "digital_semester3.pdf",
        mimeType: "application/pdf",
        buffer: fs.readFileSync(MARKSHEET),
      },
    },
  });
  expect(up.status()).toBe(201);
  const doc = (await up.json()) as { id: string; records: { fields: Record<string, unknown> }[] };
  const keys = [
    "subject_name",
    "subject_code",
    "component",
    "status",
    "marks_obtained",
    "max_marks",
    "grade",
    "grade_points",
    "credits",
    "semester",
    "exam_type",
    "exam_name",
  ];
  const results = doc.records.map((r) =>
    Object.fromEntries(keys.filter((k) => k in r.fields).map((k) => [k, r.fields[k]])),
  );
  const confirm = await request.post(`/api/documents/${doc.id}/confirm`, { data: { results } });
  expect(confirm.ok()).toBe(true);
}

export function topicCard(page: Page, name: string) {
  return page.locator("article", {
    has: page.getByRole("heading", { name, exact: true, level: 3 }),
  });
}
