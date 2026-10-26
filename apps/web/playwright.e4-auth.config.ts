import { defineConfig } from '@playwright/test';
import base from './playwright.builder-auth.config';

// Importing the existing authenticated config enforces its dedicated loopback test API guard.
const api = process.env.CIP_BUILDER_TEST_API!;

export default defineConfig({
  ...base,
  testMatch: 'e4-saved-query-auth.spec.ts',
  reporter: [['list'], ['json', { outputFile: '../../.eif/audit/EXECUTION_20261026_E4/browser-authenticated.json' }]],
  outputDir: './test-results/e4',
  use: { ...base.use, baseURL: 'http://127.0.0.1:3107', trace: 'off', screenshot: 'off', video: 'off' },
  webServer: {
    command: 'pnpm exec next dev --port 3107 --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3107/dashboards',
    reuseExistingServer: false,
    timeout: 240_000,
    env: {
      CIP_DISABLE_NEXT_API_PROXY: 'false',
      CIP_ENABLE_NEXT_API_PROXY: 'true',
      CIP_API_INTERNAL_URL: api,
      NEXT_PUBLIC_API_URL: '',
      CIP_NEXT_DIST_DIR: '.tmp/e4-browser-next',
      CIP_NEXT_TSCONFIG: 'tsconfig.e4-e2e.json',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
});
