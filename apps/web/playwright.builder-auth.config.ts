import { defineConfig } from '@playwright/test';
import base from './playwright.builder.config';

// Supplied only by the cip_test-only, rolled-back pytest harness; never a dev API default.
const api = process.env.CIP_BUILDER_TEST_API;
if (!api || !/^http:\/\/127\.0\.0\.1:\d+$/.test(api) || ['8001', '8010'].includes(new URL(api).port)) {
  throw new Error('Run the transactional cip_test pytest harness; a dedicated loopback test API is required.');
}

export default defineConfig({
  ...base,
  testMatch: 'builder-auth.spec.ts',
  timeout: 180_000,
  reporter: [['list'], ['json', { outputFile: '../../.eif/audit/PROGRAMME_20261024/browser-authenticated.json' }]],
  use: { ...base.use, trace: 'off', screenshot: 'off', video: 'off' },
  webServer: {
    command: 'pnpm exec next dev --port 3106 --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3106/design-lab/builder',
    reuseExistingServer: false,
    timeout: 240_000,
    env: {
      CIP_DISABLE_NEXT_API_PROXY: 'false',
      CIP_ENABLE_NEXT_API_PROXY: 'true',
      CIP_API_INTERNAL_URL: api,
      NEXT_PUBLIC_API_URL: '',
      CIP_NEXT_DIST_DIR: '.tmp/builder-next',
      CIP_NEXT_TSCONFIG: 'tsconfig.builder-e2e.json',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
});
