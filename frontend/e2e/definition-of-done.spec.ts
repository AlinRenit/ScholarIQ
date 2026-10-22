import type { Page } from "@playwright/test";

import { blockOutbound, createProfile, expect, MARKSHEET, test, topicCard } from "./fixtures";

// The definition-of-done walkthrough, in order, through the real UI against a
// fresh database with outbound network access blocked. Each step builds on the
// previous one, so they share one browser page.
test.describe.configure({ mode: "serial" });

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

async function ask(question: string) {
  const answers = page.locator("article");
  const before = await answers.count();
  await page.locator("#tutor-question").fill(question);
  await page.keyboard.press("Enter");
  await expect(answers).toHaveCount(before + 1);
  return answers.nth(before);
}

test("a new visitor is asked to create a profile", async () => {
  await page.goto("/");
  await expect(page.getByText("Create a profile to get started")).toBeVisible();
  await createProfile(page);
});

test("upload a marksheet, correct a value and confirm", async () => {
  await page.getByLabel("Choose a marksheet file").setInputFiles(MARKSHEET);
  await page.waitForURL(/\/academics\/import\//);

  const os = page
    .locator("ol > li")
    .filter({ has: page.locator('input[value="Operating Systems"]') });
  const marks = os.getByLabel(/Marks obtained/);
  await expect(marks).toHaveValue("52");
  // The correction: the student's real mark was 48, not the 52 that was read.
  await marks.fill("48");

  await page.getByRole("button", { name: /^Confirm and save \d+ results?$/ }).click();
  await page.waitForURL(/\/academics$/);
  await expect(page.getByText("Operating Systems").first()).toBeVisible();
});

test("the dashboard shows the analysis and the subjects that need attention", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  const attention = page.locator("section, div", {
    has: page.getByRole("heading", { name: "Subjects that may need attention" }),
  });
  await expect(attention.last()).toContainText("Database Management Systems");
  // The corrected mark (48 of 100) is what was analysed.
  await expect(attention.last()).toContainText("Operating Systems");
  await expect(attention.last()).not.toContainText("Data Structures");
});

test("topics show their evidence status, and topic results change it", async () => {
  await page.goto("/topics");
  const normalization = topicCard(page, "Normalization").first();
  await expect(normalization).toContainText("Insufficient evidence");

  async function addTest(name: string, obtained: string, max: string, questions: string) {
    const card = topicCard(page, name).first();
    await card.getByRole("button", { name: "Add a topic test result" }).click();
    await card.getByLabel("Marks obtained").fill(obtained);
    await card.getByLabel("Maximum marks").fill(max);
    await card.getByLabel("Questions").fill(questions);
    await card.getByRole("button", { name: "Save" }).click();
    return card;
  }

  await expect(await addTest("Normalization", "2", "10", "10")).toContainText("Needs attention");
  await expect(await addTest("Stacks and queues", "10", "10", "10")).toContainText("Strong");
});

test("the tutor answers from the knowledge base with sources", async () => {
  await page.goto("/tutor");
  const answer = await ask("What is a queue?");
  await expect(answer.getByRole("heading", { name: "Sources" })).toBeVisible();
});

test("a topic that needs attention gets a step-by-step answer", async () => {
  const answer = await ask("What is third normal form?");
  await expect(answer).toContainText("Step by step.");
  await expect(answer).toContainText("needs attention");
});

test("a strong topic gets a concise overview", async () => {
  const answer = await ask("What is a stack?");
  await expect(answer).toContainText("Brief overview.");
});

test("an out-of-scope question is not answered", async () => {
  const answer = await ask("Explain the Krebs cycle");
  await expect(answer.getByRole("heading", { name: "Sources" })).toHaveCount(0);
});

test("an answer states its limits", async () => {
  const answer = await ask(
    "What is the time complexity of this?\n```python\nfor i in range(n):\n    for j in range(n):\n        print(i, j)\n```",
  );
  await expect(answer.getByRole("heading", { name: "Limits of this answer" })).toBeVisible();
  await expect(answer).toContainText("without running it");
});

test("a diagnostic quiz updates the topic evidence", async () => {
  await page.goto("/topics");
  await topicCard(page, "Normalization")
    .first()
    .getByRole("button", { name: "Take a diagnostic quiz" })
    .click();
  await page.waitForURL(/\/practice\/quiz\//);

  const groups = page.locator("fieldset");
  await expect(groups.first()).toBeVisible();
  const n = await groups.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) await groups.nth(i).getByRole("radio").first().check();
  await page.getByRole("button", { name: "Submit answers" }).click();

  const result = page.getByRole("region", { name: "Quiz result" });
  await expect(result).toContainText(`of ${n} correct`);
  await expect(result).toContainText("Needs attention"); // the classification before

  await page.goto("/topics");
  const card = topicCard(page, "Normalization").first();
  await card.getByText(/^Evidence \(\d+\)$/).click();
  await expect(card).toContainText(/Diagnostic quiz: \d+ of \d+ correct/);
});

test("the study plan is built with its reasons", async () => {
  await page.goto("/study-plan");
  await page.getByRole("button", { name: "Build my plan" }).click();
  const items = page.locator("ol > li");
  await expect(items.first()).toBeVisible();
  await expect(page.locator("ol")).toContainText("Normalization");
  // Strong topics are left out unless chosen as a goal, and the page says so.
  await expect(page.getByText(/Stacks and queues.*Choose one as a goal/)).toBeVisible();
  await items.first().locator("summary").first().click();
  await expect(items.first()).toContainText(/priority|Priority/);
});

test("unreviewed content and privacy terms are labelled", async () => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
  await page.goto("/knowledge-base");
  await expect(page.getByText(/not yet reviewed/i).first()).toBeVisible();
});

test("delete my data removes the profile", async () => {
  await page.goto("/settings");
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Delete my data" }).click();
  await expect(page.getByText("All your data has been deleted.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete my data" })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByText("Create a profile to get started")).toBeVisible();
});
