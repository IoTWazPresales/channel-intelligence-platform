/**
 * Celery beat scheduler for periodic maintenance tasks (running-job reaper, etc.).
 * Requires Redis (same as dev:worker). Run alongside dev:worker.
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const apiRoot = path.join(__dirname, '..', 'apps', 'api');
const isWin = process.platform === 'win32';
const py = path.join(apiRoot, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

if (!fs.existsSync(py)) {
  console.error(`Missing venv at ${py} — run pnpm dev:api setup first.`);
  process.exit(1);
}

const args = ['-m', 'celery', '-A', 'app.worker.celery_app', 'beat', '-l', 'info'];
const child = spawn(py, args, { cwd: apiRoot, stdio: 'inherit', env: process.env });

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
