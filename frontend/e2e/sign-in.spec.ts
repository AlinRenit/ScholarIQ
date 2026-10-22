import { blockOutbound, createProfile, expect, test } from "./fixtures";

const EMAIL = "e2e.student@example.test";
const PASSWORD = "correct horse battery";

test("a password lets the student sign in elsewhere and sign out everywhere", async ({
  page,
  browser,
}) => {
  await createProfile(page, "Signing Student");
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Sign-in and security" })).toBeVisible();
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByLabel("Repeat password").fill(PASSWORD);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Password set" })).toBeVisible();

  // A second browser with no cookie.
  const other = await browser.newContext();
  const outbound = await blockOutbound(other);
  const second = await other.newPage();
  await second.goto("/academics");
  const form = second.getByRole("form", { name: "Already have a profile?" });
  await form.getByLabel("Email").fill(EMAIL);
  await form.getByLabel("Password").fill("not the password");
  await form.getByRole("button", { name: "Sign in" }).click();
  await expect(form.getByRole("alert")).toBeVisible();
  await form.getByLabel("Password").fill(PASSWORD);
  await form.getByRole("button", { name: "Sign in" }).click();
  await expect(second.getByRole("heading", { name: "Import a marksheet" })).toBeVisible();

  // Signing out everywhere from the second browser ends the first one's session too.
  await second.goto("/settings");
  await second.getByRole("button", { name: "Sign out everywhere" }).click();
  await second.waitForURL(/\/academics$/);
  await expect(second.getByRole("button", { name: "Create profile" })).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByText("No profile on this browser.")).toBeVisible();

  await other.close();
  expect(outbound).toEqual([]);
});
