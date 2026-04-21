/**
 * Run arbitrary Python from apps/api using the project venv (same resolution as dev-api.js).
 * Usage (repo root): node scripts/run-api-python.cjs scripts/wipe_database.py
 *                     node scripts/run-api-python.cjs -m alembic upgrade head
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const apiRoot = path.join(__dirname, '..', 'apps', 'api');
const isWin = process.platform === 'win32';
const py = path.join(apiRoot, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

if (!fs.existsSync(py)) {
  console.error(
    `Missing venv at ${py}\n` +
      'From apps/api: py -3.12 -m venv .venv && .venv\\Scripts\\activate && pip install -r requirements.txt\n'
  );
  process.exit(1);
}

const pyArgs = process.argv.slice(2);
if (!pyArgs.length) {
  console.error(
    'Usage: node scripts/run-api-python.cjs <args passed to python...>\n' +
      'Examples:\n' +
      '  node scripts/run-api-python.cjs scripts/wipe_database.py\n' +
      '  node scripts/run-api-python.cjs -m alembic upgrade head\n' +
      '  node scripts/run-api-python.cjs scripts/seed.py'
  );
  process.exit(1);
}

const r = spawnSync(py, pyArgs, { cwd: apiRoot, stdio: 'inherit', env: process.env, shell: false });
process.exit(r.status ?? 1);
