/**
 * Same as parallel dev:api + dev:web + dev:worker, with a stderr notice that the worker needs Redis.
 */
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.join(__dirname, '..');

const env = {
  ...process.env,
  CIP_API_PORT: process.env.CIP_API_PORT || '8001',
  CIP_API_INTERNAL_URL: process.env.CIP_API_INTERNAL_URL || 'http://127.0.0.1:8001',
};

console.error(
  '[cip-dev] pnpm dev:all runs API + web + Celery worker in parallel.\n' +
    '[cip-dev] Local port contract for this repo: web :3000, API :8001.\n' +
    '[cip-dev] The worker expects Redis at CELERY_BROKER_URL (default redis://localhost:6379/1).\n' +
    '[cip-dev] Without Redis, omit the worker: run `pnpm dev:api` and `pnpm dev:web` in two terminals, and see docs/LOCAL_DEV_WINDOWS.md (CIP_DEV_CELERY_DISPATCH for PM commit only).\n' +
    '[cip-dev] With Redis: `pnpm dev:worker` preflights broker TCP, uses --pool=solo on Windows, and embeds beat (--beat).\n'
);

const r = spawnSync('pnpm', ['exec', 'npm-run-all', '--parallel', 'dev:api', 'dev:web', 'dev:worker'], {
  cwd: root,
  stdio: 'inherit',
  env,
  shell: true,
});
process.exit(r.status ?? 1);
