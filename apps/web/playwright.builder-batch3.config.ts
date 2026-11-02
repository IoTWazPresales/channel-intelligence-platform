import { defineConfig, devices } from '@playwright/test';

// GOV-008 batch 3 render of the chart cases. Fixture page, no API: every /api/v1 request is refused by the spec.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'builder-batch3-render.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 30_000 },
  reporter: [['list']],
  outputDir: './test-results/builder-batch3',
  use: { baseURL: 'http://127.0.0.1:3107', trace: 'off', screenshot: 'off', video: 'off', contextOptions: { reducedMotion: 'reduce' } },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'node node_modules/next/dist/bin/next dev --port 3107 --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3107/design-lab/builder-batch3',
    reuseExistingServer: false,
    timeout: 300_000,
    env: {
      CIP_DISABLE_NEXT_API_PROXY: 'true',
      CIP_NEXT_DIST_DIR: '.tmp/batch3-next',
      CIP_NEXT_TSCONFIG: 'tsconfig.builder-e2e.json',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
});
