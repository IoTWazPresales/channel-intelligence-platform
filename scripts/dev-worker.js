/**
 * Run Celery worker using apps/api/.venv (same pattern as scripts/dev-api.js).
 *
 * - Preflight: TCP connect to the host:port from CELERY_BROKER_URL (default 127.0.0.1:6379) so the worker
 *   fails fast with a clear message when Redis is not listening (common no-Docker Windows gap).
 * - Windows: defaults to --pool=solo (prefork is unreliable on Windows). Override with CIP_CELERY_WORKER_POOL.
 * - Local dev beat: disabled by default on Windows solo (BACKLOG-038). Set CIP_ENABLE_DEV_BEAT=1 to spawn beat.
 *   Unix/macOS embed via worker --beat unless CIP_DISABLE_DEV_BEAT=1.
 * - Worker subscribes to -Q interactive,batch,celery (interactive first).
 * - Skip preflight only when explicitly needed: CIP_SKIP_REDIS_PREFLIGHT=1 (not for normal local dev).
 */
const { spawn } = require('child_process');
const fs = require('fs');
const net = require('net');
const path = require('path');
const { URL } = require('url');

const pidDir = path.join(__dirname, '..', '.cip-dev-pids');
const pidFile = path.join(pidDir, 'worker.pid');

function writePid() {
  try {
    fs.mkdirSync(pidDir, { recursive: true });
    fs.writeFileSync(pidFile, String(process.pid), 'utf8');
  } catch { /* non-fatal */ }
}

function deletePid() {
  try { fs.unlinkSync(pidFile); } catch { /* already gone */ }
}

const apiRoot = path.join(__dirname, '..', 'apps', 'api');
const isWin = process.platform === 'win32';
const py = path.join(apiRoot, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

/** @type {import('child_process').ChildProcess[]} */
const children = [];
let shuttingDown = false;

function shutdownChildren() {
  shuttingDown = true;
  for (const child of children) {
    try {
      child.kill();
    } catch { /* already gone */ }
  }
}

function brokerTcpTargetFromEnv() {
  const raw = process.env.CELERY_BROKER_URL || 'redis://127.0.0.1:6379/1';
  try {
    const u = new URL(raw);
    const host = u.hostname && u.hostname.length ? u.hostname : '127.0.0.1';
    const port = u.port ? parseInt(u.port, 10) : 6379;
    return { host, port: Number.isFinite(port) && port > 0 ? port : 6379 };
  } catch {
    return { host: '127.0.0.1', port: 6379 };
  }
}

function checkBrokerTcp({ host, port }, timeoutMs) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host, port }, () => {
      socket.destroy();
      resolve();
    });
    socket.setTimeout(timeoutMs);
    socket.on('error', (err) => {
      socket.destroy();
      reject(err);
    });
    socket.on('timeout', () => {
      socket.destroy();
      reject(new Error(`TCP connect timeout after ${timeoutMs}ms`));
    });
  });
}

function spawnCelery(subcommand, extraArgs = []) {
  const args = ['-m', 'celery', '-A', 'app.worker.celery_app', subcommand, '-l', 'info', ...extraArgs];
  const child = spawn(py, args, { cwd: apiRoot, stdio: 'inherit', env: process.env });
  children.push(child);
  return child;
}

function onChildExit(code, signal) {
  if (shuttingDown) return;
  shutdownChildren();
  deletePid();
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
}

async function main() {
  writePid();
  process.on('exit', deletePid);
  process.on('SIGTERM', () => {
    shutdownChildren();
    deletePid();
    process.exit(0);
  });
  process.on('SIGINT', () => {
    shutdownChildren();
    deletePid();
    process.exit(130);
  });

  if (!fs.existsSync(py)) {
    console.error(
      `Missing venv at ${py}\n` +
        'Create it from apps/api (see dev-api.js message), then:\n' +
        '  pip install -r requirements.txt\n'
    );
    process.exit(1);
  }

  if (process.env.CIP_SKIP_REDIS_PREFLIGHT === '1') {
    console.error(
      '[cip-dev-worker] CIP_SKIP_REDIS_PREFLIGHT=1 — skipping Redis TCP preflight (for automation/unusual setups only).'
    );
  } else {
    const t = brokerTcpTargetFromEnv();
    const timeoutMs = Number(process.env.CIP_REDIS_PREFLIGHT_TIMEOUT_MS || 3000);
    try {
      await checkBrokerTcp(t, timeoutMs);
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      console.error(
        `[cip-dev-worker] Cannot reach Redis at ${t.host}:${t.port} (parsed from CELERY_BROKER_URL).\n` +
          `  Product Master commit and other Celery tasks need a broker. Start Redis (Memurai, WSL redis-server, etc.)\n` +
          `  so it listens on that host/port, or point CELERY_BROKER_URL / CELERY_RESULT_BACKEND at your broker.\n` +
          `  See docs/LOCAL_DEV_WINDOWS.md. Last error: ${msg}\n` +
          `  (To skip this check in special cases only: CIP_SKIP_REDIS_PREFLIGHT=1)`
      );
      process.exit(1);
    }
  }

  const workerExtra = [];
  const poolOverride = process.env.CIP_CELERY_WORKER_POOL;
  const soloPool = !poolOverride || poolOverride === 'solo';
  const disableBeat =
    process.env.CIP_DISABLE_DEV_BEAT === '1' ||
    (isWin && soloPool && process.env.CIP_ENABLE_DEV_BEAT !== '1');

  if (poolOverride) {
    workerExtra.push('--pool', poolOverride);
    console.error(`[cip-dev-worker] Using Celery --pool=${poolOverride} (from CIP_CELERY_WORKER_POOL).`);
  } else if (isWin) {
    workerExtra.push('--pool', 'solo');
    console.error(
      '[cip-dev-worker] Windows: using Celery --pool=solo (reliable default). Override with CIP_CELERY_WORKER_POOL=prefork|threads|gevent|...'
    );
  }

  workerExtra.push('-Q', 'interactive,batch,celery');
  console.error(
    '[cip-dev-worker] Subscribing to queues interactive,batch,celery (interactive first for steward work).'
  );

  if (disableBeat) {
    console.error(
      '[cip-dev-worker] Celery beat disabled (Windows solo default). Set CIP_ENABLE_DEV_BEAT=1 to run periodic reaper locally.'
    );
  } else if (isWin) {
    console.error(
      '[cip-dev-worker] Windows: spawning sibling celery beat (worker --beat is unsupported on Windows).'
    );
    const beat = spawnCelery('beat');
    beat.on('exit', onChildExit);
  } else {
    workerExtra.push('--beat');
    console.error('[cip-dev-worker] Embedded Celery beat enabled (--beat) for periodic maintenance tasks.');
  }

  const worker = spawnCelery('worker', workerExtra);
  worker.on('exit', onChildExit);
}

main().catch((e) => {
  console.error('[cip-dev-worker] startup error:', e);
  process.exit(1);
});
