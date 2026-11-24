import { defineConfig, devices } from "@playwright/test";
import { E2E_SESSION_SECRET } from "./e2e/auth";

const PORT = process.env.PORT || 3000;
const baseURL = process.env.BASE_URL || `http://localhost:${PORT}`;

/**
 * Playwright E2E: Chromium, Microsoft Edge ve Firefox (#116, #155)
 */
export default defineConfig({
  testDir: "./e2e",
  // Varsayılan oturum yönetici; sahip senaryoları `e2e/fixtures.ts` ile sahip çerezini kullanır (#372).
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    storageState: "e2e/.auth/admin.json",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "msedge",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
    env: {
      NEXT_PUBLIC_USE_MOCKS: process.env.NEXT_PUBLIC_USE_MOCKS ?? "true",
      SESSION_SECRET: E2E_SESSION_SECRET,
    },
  },
});
