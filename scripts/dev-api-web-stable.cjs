/**
 * Deterministic local API+web startup for native dev.
 * - API always binds to 8001
 * - Next same-origin proxy always targets API 8001
 */
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.join(__dirname, '..');

const env = {
  ...process.env,
  CIP_API_PORT: '8001',
  CIP_API_PROXY_TARGET: 'http://127.0.0.1:8001',
};

// Prevent accidental cross-origin direct browser targeting in this mode.
delete env.NEXT_PUBLIC_API_URL;

const r = spawnSync('pnpm', ['exec', 'npm-run-all', '--parallel', 'dev:api', 'dev:web'], {
  cwd: root,
  stdio: 'inherit',
  env,
  shell: true,
});
process.exit(r.status ?? 1);
