/**
 * Run Playwright e2e. Default API URL is Docker host port :8010.
 * Native stack: set CIP_E2E_API_URL=http://127.0.0.1:8000 before `pnpm docker:e2e` (or run `pnpm test:e2e` from apps/web).
 * Usage (Docker API): `pnpm docker:up:detached` then `pnpm docker:e2e`.
 */
const { spawnSync } = require('child_process');
const path = require('path');

if (!process.env.CIP_E2E_API_URL) {
  process.env.CIP_E2E_API_URL = 'http://127.0.0.1:8010';
}

const cwd = path.join(__dirname, '..', 'apps', 'web');
const r = spawnSync('npx', ['playwright', 'test'], {
  cwd,
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: process.env,
});
process.exit(r.status ?? 1);
