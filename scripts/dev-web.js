/**
 * Run Next dev server with deterministic local proxy target.
 * Local contract: web :3000 -> API :8001.
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const pidDir = path.join(__dirname, '..', '.cip-dev-pids');
const pidFile = path.join(pidDir, 'web.pid');

function writePid() {
  try {
    fs.mkdirSync(pidDir, { recursive: true });
    fs.writeFileSync(pidFile, String(process.pid), 'utf8');
  } catch { /* non-fatal */ }
}

function deletePid() {
  try { fs.unlinkSync(pidFile); } catch { /* already gone */ }
}

writePid();
process.on('exit', deletePid);
process.on('SIGTERM', () => { deletePid(); process.exit(0); });
process.on('SIGINT', () => { deletePid(); process.exit(0); });

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
