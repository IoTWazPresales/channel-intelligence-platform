import { defineConfig, devices } from '@playwright/test';

/**
 * CI enables live API e2e via CIP_E2E_LIVE_API + CIP_E2E_API_URL (BACKLOG-099).
 * Without those vars, Next proxy is disabled so mocked/static specs stay API-free.
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
      // Proxy to live API when CIP_E2E_* is set; otherwise disable to avoid :8001 ECONNREFUSED.
      CIP_DISABLE_NEXT_API_PROXY: process.env.CIP_E2E_API_URL || process.env.CIP_E2E_LIVE_API ? 'false' : 'true',
    },
  },
});
