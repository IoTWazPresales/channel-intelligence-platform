import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'builder*.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [['list'], ['json', { outputFile: '../../.eif/audit/PROGRAMME_20261024/browser-results.json' }]],
  outputDir: './test-results/builder',
  use: { baseURL: 'http://127.0.0.1:3106', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm exec next dev --port 3106 --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3106/design-lab/builder',
    reuseExistingServer: false,
    timeout: 240_000,
    env: {
      CIP_DISABLE_NEXT_API_PROXY: 'true',
      CIP_NEXT_DIST_DIR: '.tmp/builder-next',
      CIP_NEXT_TSCONFIG: 'tsconfig.builder-e2e.json',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
});
