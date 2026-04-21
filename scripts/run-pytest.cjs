const fs = require('fs');
const { spawnSync } = require('child_process');
const path = require('path');

const cwd = path.resolve(__dirname, '..', 'apps', 'api');
const fromEnv = process.env.PYTHON;
const venvPython =
  process.platform === 'win32'
    ? path.join(cwd, '.venv', 'Scripts', 'python.exe')
    : path.join(cwd, '.venv', 'bin', 'python3');
const preferVenv = fs.existsSync(venvPython) ? [venvPython] : [];
const candidates = fromEnv
  ? [fromEnv]
  : [...preferVenv, ...(process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'])];
let status = 1;
for (const cmd of candidates) {
  const r = spawnSync(cmd, ['-m', 'pytest', 'tests', '-q'], { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
  if (r.error && r.error.code === 'ENOENT') continue;
  status = r.status ?? 1;
  break;
}
process.exit(status);
