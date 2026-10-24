import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { blockOutbound, createProfile, expect, test } from "./fixtures";

// Question-level exam analysis through the real UI: upload a question paper,
// review it, enter marks, map topics, confirm and read the analysis.
test.describe.configure({ mode: "serial" });

const PAPER = path.resolve(
  __dirname,
  "../../backend/tests/fixtures/question_papers/digital_ds_paper.pdf",
);

let page: Page;
let outbound: string[];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext();
  outbound = await blockOutbound(context);
  page = await context.newPage();
});

test.afterAll(async () => {
  await page.context().close();
  expect(outbound, "requests to hosts other than this machine").toEqual([]);
});

function card(label: string) {
  return page.getByRole("listitem", { name: `Question ${label}`, exact: true });
}

async function axe(where: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious.map((v) => `${where} ${v.id}: ${v.help}`)).toEqual([]);
}

test("start a breakdown for a subject", async () => {
  await createProfile(page, "Exam Student");
  await page.goto("/exam-breakdown");
  await expect(page.getByText("No exam breakdowns yet")).toBeVisible();
  await page.getByLabel("Subject").selectOption({ label: "Data Structures" });
  await page.getByLabel("Name (optional)").fill("Series test 1");
  await page.getByRole("button", { name: "Create breakdown" }).click();
  await page.waitForURL(/\/exam-breakdown\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Series test 1", level: 1 })).toBeVisible();
});

test("upload the question paper and review what was read", async () => {
  await page.getByLabel("Choose a question paper file").setInputFiles(PAPER);
  await expect(page.getByText(/Found 8 question\(s\)/)).toBeVisible();
  await expect(card("4(a)").getByLabel("Maximum marks")).toHaveValue("6");
  await expect(card("6").getByLabel("Optional (part of a choice)")).toBeChecked();
  await axe("editor");
});

test("a mark above the maximum is refused before saving", async () => {
  await card("1").getByLabel("Marks obtained").fill("3");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(card("1").getByRole("alert")).toHaveText(/cannot be more than the maximum/);
  await card("1").getByLabel("Marks obtained").fill("2");
});

test("enter marks, map topics and confirm", async () => {
  const marks: [string, string][] = [
    ["2", "1"],
    ["3", "0"],
    ["4(a)", "3"],
    ["4(b)", "2"],
    ["5", "4"],
    ["7", "6"],
  ];
  for (const [label, value] of marks) {
    await card(label).getByLabel("Marks obtained").fill(value);
  }
  await card("6").getByLabel("Attempt").selectOption("not_attempted");

  const useAll = page.getByRole("button", { name: /Use \d+ clear topic suggestion/ });
  if (await useAll.isVisible()) await useAll.click();
  // Map any question still without a topic by hand, so every question counts.
  for (const [label, topic] of [
    ["1", "Stacks and queues"],
    ["3", "Trees and binary search trees"],
    ["7", "Sorting and searching"],
  ] as const) {
    if (
      await card(label)
        .getByText(/^Not mapped/)
        .isVisible()
    ) {
      await card(label).getByLabel("Add a topic").selectOption({ label: topic });
    }
  }
  await expect(page.getByText(/^Not mapped/)).toHaveCount(0);

  await page.getByRole("button", { name: "Save and confirm" }).click();
  await page.waitForURL(/\/analysis$/);
});

test("the analysis shows overall, module and topic results", async () => {
  // 2+1+0+3+2+4+6 of 2+2+2+6+4+10+8: Q6 was the unchosen option.
  await expect(page.getByText("52.9%")).toBeVisible();
  await expect(page.getByText(/18 of 34 marks, from 7 of 8 question/)).toBeVisible();
  await expect(page.getByText(/Not counted \(.*\): Q6/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "By module" })).toBeVisible();
  await expect(page.getByText("▲ Needs the most attention")).toBeVisible();
  const first = page.getByRole("button", { name: "Show topics and questions" }).first();
  const controls = await first.getAttribute("aria-controls");
  const toggle = page.locator(`button[aria-controls="${controls}"]`);
  await toggle.click();
  await expect(page.locator(`[id="${controls}"]`)).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText(/Exam performance is how you scored on this paper/)).toBeVisible();
  await axe("analysis");
});

test("the dashboard and Topics page point to the weak module", async () => {
  await page.goto("/");
  await expect(page.getByText(/Exam questions \(1 confirmed exam\)/)).toBeVisible();
  await expect(page.getByText(/Module needing the most attention/)).toBeVisible();
  await page.goto("/topics");
  await expect(page.getByText(/Exam questions \(1 confirmed exam\)/)).toBeVisible();
});

test("returning to draft removes the exam from the analysis", async () => {
  await page.goto("/exam-breakdown");
  await page.getByRole("link", { name: "Series test 1" }).click();
  await page.getByRole("button", { name: "Return to draft" }).click();
  await expect(page.getByText(/Returned to draft/)).toBeVisible();
  await page.goto("/exam-breakdown");
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await page.goto("/topics");
  await expect(page.getByText(/Exam questions \(1 confirmed exam\)/)).toHaveCount(0);
});
