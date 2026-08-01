import { defineConfig, devices } from '@playwright/test';

/**
 * CI runs mocked / static e2e only (Next webServer, no FastAPI).
 * Live API specs (`wipe-and-products-delete`) require CIP_E2E_API_URL / CIP_E2E_LIVE_API — see BACKLOG-099.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm exec next dev --port 3000 --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      // Avoid Next proxy → :8001 ECONNREFUSED spam when CI has no API process.
      // Browser `page.route` mocks still intercept `/api/v1/**` for mocked specs.
      CIP_DISABLE_NEXT_API_PROXY: process.env.CIP_E2E_API_URL || process.env.CIP_E2E_LIVE_API ? 'false' : 'true',
    },
  },
});
