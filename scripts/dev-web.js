/**
 * Run Next dev server with deterministic local proxy target.
 * Local contract: web :3000 -> API :8001.
 */
const { spawn } = require('child_process');

const env = {
  ...process.env,
  CIP_API_INTERNAL_URL: process.env.CIP_API_INTERNAL_URL || 'http://127.0.0.1:8001',
};

const child = spawn('pnpm', ['--filter', '@cip/web', 'dev'], {
  stdio: 'inherit',
  env,
  shell: true,
});

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
