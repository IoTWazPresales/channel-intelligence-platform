import { defineConfig } from '@playwright/test';
import base from './playwright.builder.config';

// Supplied only by the cip_test-only, rolled-back pytest harness (test_dashboard_polish_render.py).
const api = process.env.CIP_BUILDER_TEST_API;
if (!api || !/^http:\/\/127\.0\.0\.1:\d+$/.test(api) || ['8001', '8010'].includes(new URL(api).port)) {
  throw new Error('Run the transactional cip_test pytest harness; a dedicated loopback test API is required.');
}

const env = (dist: string) => ({
  CIP_DISABLE_NEXT_API_PROXY: 'false',
  CIP_ENABLE_NEXT_API_PROXY: 'true',
  CIP_API_INTERNAL_URL: api,
  NEXT_PUBLIC_API_URL: '',
  CIP_NEXT_DIST_DIR: dist,
  CIP_NEXT_TSCONFIG: 'tsconfig.builder-e2e.json',
  NEXT_TELEMETRY_DISABLED: '1',
});

// "after" = this working tree on :3106. "before" = a HEAD worktree's apps/web on :3107 (optional).
const before = process.env.CIP_POLISH_BEFORE_DIR;

export default defineConfig({
  ...base,
  testMatch: 'dashboard-polish-render.spec.ts',
  timeout: 900_000,
  reporter: [['list']],
  use: { ...base.use, trace: 'off', screenshot: 'off', video: 'off' },
  webServer: [
    {
      command: 'node node_modules/next/dist/bin/next dev --port 3106 --hostname 127.0.0.1',
      url: 'http://127.0.0.1:3106/design-lab/builder',
      reuseExistingServer: false,
      timeout: 300_000,
      env: env('.tmp/polish-after'),
    },
    ...(before
      ? [{
          command: 'node node_modules/next/dist/bin/next dev --port 3107 --hostname 127.0.0.1',
          cwd: before,
          url: 'http://127.0.0.1:3107/design-lab/builder',
          reuseExistingServer: false,
          timeout: 300_000,
          env: env('.tmp/polish-before'),
        }]
      : []),
  ],
});
