/**
 * Run Celery worker using apps/api/.venv (same pattern as scripts/dev-api.js).
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const apiRoot = path.join(__dirname, '..', 'apps', 'api');
const isWin = process.platform === 'win32';
const py = path.join(apiRoot, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

if (!fs.existsSync(py)) {
  console.error(
    `Missing venv at ${py}\n` +
      'Create it from apps/api (see dev-api.js message), then:\n' +
      '  pip install -r requirements.txt\n'
  );
  process.exit(1);
}

const child = spawn(
  py,
  ['-m', 'celery', '-A', 'app.worker.celery_app', 'worker', '-l', 'info'],
  { cwd: apiRoot, stdio: 'inherit', env: process.env }
);

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
