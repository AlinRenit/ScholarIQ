import AxeBuilder from "@axe-core/playwright";

import { createProfile, expect, importMarksheet, test } from "./fixtures";

// Automated WCAG 2.1 A/AA checks on every main page with real data on it.
// axe finds a subset of accessibility problems; keyboard and screen-reader
// checks are still done by hand (see docs/ACCESSIBILITY.md).
const PAGES = [
  "/",
  "/academics",
  "/exam-breakdown",
  "/topics",
  "/tutor",
  "/practice",
  "/study-plan",
  "/knowledge-base",
  "/knowledge-base?q=stack",
  "/knowledge-base/concepts/ds.stack",
  "/knowledge-base/topics/ds.stacks-queues",
  "/settings",
];

test("main pages have no serious or critical axe violations", async ({ page }) => {
  await createProfile(page, "Axe Student");
  await importMarksheet(page.request);

  const problems: string[] = [];
  async function scan(path: string, prepare?: () => Promise<void>) {
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      if (prepare) await prepare();
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      for (const v of result.violations) {
        const where = v.nodes.map((n) => n.target.join(" ")).slice(0, 3);
        if (v.impact !== "serious" && v.impact !== "critical") {
          // Reported, not failed on: listed in the run output for follow-up.
          console.log(
            `axe ${v.impact}: ${path} (${scheme}) ${v.id}: ${v.help} at ${where.join(", ")}`,
          );
          continue;
        }
        problems.push(
          `${path} (${scheme}) ${v.id} [${v.impact}]: ${v.help} at ${where.join(", ")}`,
        );
      }
    }
  }

  for (const path of PAGES) await scan(path);
  // Pages whose content appears after an action.
  await scan("/tutor", async () => {
    await page.locator("#tutor-question").fill("What is a stack?");
    await page.keyboard.press("Enter");
    await expect(page.locator("article")).toHaveCount(1);
  });
  await page.goto("/practice");
  await page.getByRole("button", { name: /quiz/i }).first().click();
  await page.waitForURL(/\/practice\/quiz\//);
  await scan(new URL(page.url()).pathname);
  await scan("/study-plan", async () => {
    const build = page.getByRole("button", { name: /Build my plan|Rebuild plan/ });
    await build.click();
    await expect(page.locator("ol > li").first()).toBeVisible();
  });
  expect(problems, problems.join("\n")).toEqual([]);
});

test("keyboard users can skip to the content and every page fits a phone screen", async ({
  page,
}) => {
  await createProfile(page, "Keyboard Student");
  await importMarksheet(page.request);

  await page.goto("/topics");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);

  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of PAGES) {
    await page.goto(path);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path} scrolls sideways on a 390px screen`).toBeLessThanOrEqual(0);
  }
});
