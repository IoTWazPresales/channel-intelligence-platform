import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

import { parseMode } from './src/lib/verification/matrix';

/**
 * Wave 2 verification matrix (docs/audits/WAVE2_VERIFICATION_HARNESS.md).
 *
 * No webServer: this config only drives an app that is already running, named by
 * CIP_VERIFY_BASE_URL. CIP_VERIFY_MODE is required:
 *   readonly  the live app; one worker, no retries, only the `loaded` state, every write aborted.
 *   full      the test instance; all states (browser-side intercepts), writes still aborted unless
 *             CIP_VERIFY_ALLOW_WRITES=1 is set explicitly.
 */
const baseURL = process.env.CIP_VERIFY_BASE_URL?.trim();
if (!baseURL) {
  throw new Error(
    'CIP_VERIFY_BASE_URL is required (the running web app, e.g. the test instance URL). This config never starts a server.',
  );
}
let parsed: URL;
try {
  parsed = new URL(baseURL);
} catch {
  throw new Error(`CIP_VERIFY_BASE_URL is not a URL: ${JSON.stringify(baseURL)}`);
}
if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
  throw new Error(`CIP_VERIFY_BASE_URL must be http(s); got ${parsed.protocol}`);
}
const mode = parseMode(process.env.CIP_VERIFY_MODE?.trim());
const readonly = mode === 'readonly';
// One id per run for every results/figures line; worker processes inherit it from the runner.
process.env.CIP_VERIFY_RUN_ID ||= new Date().toISOString();
const outDir = path.resolve(__dirname, '.tmp', 'wave2');

export default defineConfig({
  testDir: './e2e',
  testMatch: 'wave2-matrix.spec.ts',
  fullyParallel: !readonly,
  workers: readonly ? 1 : undefined,
  retries: 0,
  forbidOnly: true,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  outputDir: path.join(outDir, 'test-results'),
  reporter: [['list'], ['json', { outputFile: path.join(outDir, 'report.json') }]],
  use: {
    baseURL: parsed.origin,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    // Service workers could answer requests outside page.route; the write guard must see all of them.
    serviceWorkers: 'block',
    acceptDownloads: false,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
