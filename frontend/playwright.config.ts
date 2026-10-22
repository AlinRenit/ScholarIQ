import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a throwaway stack (fresh SQLite database,
// production build of the web app) with outbound network access blocked.
// See e2e/start-stack.sh and docs in the README.
const API_PORT = process.env.E2E_API_PORT ?? "8100";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "3100";
const E2E_DIR = process.env.E2E_DIR ?? path.join(os.tmpdir(), "scholariq-e2e");
process.env.E2E_DIR = E2E_DIR;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalTeardown: "./e2e/no-outbound.ts",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "bash e2e/start-stack.sh",
    url: `http://127.0.0.1:${WEB_PORT}/api/health/ready`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: { E2E_DIR, E2E_API_PORT: API_PORT, E2E_WEB_PORT: WEB_PORT },
    stdout: "ignore",
    stderr: "pipe",
  },
});
