/**
 * Run FastAPI with uvicorn using apps/api/.venv (cross-platform).
 * Avoids picking up a wrong global `python` (e.g. 3.14 on PATH).
 *
 * Before bind: verifies this checkout registers dev wipe routes, then probes the
 * listen port so a stale or foreign process cannot silently serve the wrong OpenAPI.
 * Skip with CIP_SKIP_API_PORT_PREFLIGHT=1 (emergency only).
 */
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const pidDir = path.join(__dirname, '..', '.cip-dev-pids');
const pidFile = path.join(pidDir, 'api.pid');

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

const isWin = process.platform === 'win32';

const apiRoot = path.join(__dirname, '..', 'apps', 'api');
const py = path.join(apiRoot, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

const OPENAPI_MARKER = '"/api/v1/dev/database-wipe"';

if (!fs.existsSync(py)) {
  console.error(
    `Missing venv at ${py}\n` +
      'Create it with Python 3.12 from apps/api:\n' +
      '  py -3.12 -m venv .venv\n' +
      '  .venv\\\\Scripts\\\\activate\n' +
      '  pip install -r requirements.txt\n' +
      '  alembic upgrade head\n'
  );
  process.exit(1);
}

try {
  const out = execFileSync(
    py,
    [
      '-c',
      'import pathlib; import app.api.v1.endpoints.products as m; print(pathlib.Path(m.__file__).resolve())',
    ],
    { cwd: apiRoot, encoding: 'utf8' }
  );
  console.error('[cip-dev-api] products routes module:', out.trim());
} catch (e) {
  console.error('[cip-dev-api] could not resolve products.py:', e?.message ?? e);
}

const routeCheck = [
  'from app.main import app',
  'paths={getattr(r,"path",None) for r in app.routes}',
  'assert "/api/v1/dev/database-wipe" in paths, "missing /api/v1/dev/database-wipe in app.routes"',
  'print("[cip-dev-api] verified: GET /api/v1/dev/database-wipe is registered")',
].join('\n');

try {
  execFileSync(py, ['-c', routeCheck], { cwd: apiRoot, encoding: 'utf8', stdio: 'inherit' });
} catch {
  process.exit(1);
}

/**
 * Kill the process listening on port (Windows: netstat; Unix: lsof).
 * @returns {boolean} true if a process was killed
 */
function killProcessOnPort(port) {
  try {
    if (isWin) {
      const out = execFileSync('netstat', ['-ano'], { encoding: 'utf8' });
      const pids = new Set();
      for (const line of out.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed.includes('LISTENING')) continue;
        if (!new RegExp(`:${port}\\s`).test(trimmed)) continue;
        const parts = trimmed.split(/\s+/);
        const pid = parseInt(parts[parts.length - 1], 10);
        if (pid > 4) pids.add(pid);
      }
      let killed = false;
      for (const pid of pids) {
        try {
          execFileSync('taskkill', ['/PID', String(pid), '/F'], { stdio: 'ignore' });
          console.error(`[cip-dev-api] killed stale process PID ${pid} on port ${port}`);
          killed = true;
        } catch {
          /* already gone */
        }
      }
      return killed;
    }
    const out = execFileSync('lsof', ['-ti', `tcp:${port}`], { encoding: 'utf8' }).trim();
    if (!out) return false;
    for (const pid of out.split(/\s+/)) {
      if (!pid) continue;
      try {
        process.kill(parseInt(pid, 10), 'SIGTERM');
        console.error(`[cip-dev-api] killed stale process PID ${pid} on port ${port}`);
      } catch {
        /* ignore */
      }
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * @returns {Promise<string|null>} error message or null if OK to start uvicorn
 */
function preflightListenPort() {
  if (process.env.CIP_SKIP_API_PORT_PREFLIGHT === '1') {
    console.error('[cip-dev-api] skipping port/OpenAPI preflight (CIP_SKIP_API_PORT_PREFLIGHT=1)');
    return Promise.resolve(null);
  }
  const port = Number(process.env.CIP_API_PORT || 8001);
  const host = '127.0.0.1';

  return new Promise((resolve) => {
    const req = http.get(
      {
        hostname: host,
        port,
        path: '/openapi.json',
        timeout: 4000,
        headers: { Accept: 'application/json' },
      },
      (res) => {
        const maxBytes = 512 * 1024;
        let received = 0;
        let text = '';

        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          received += chunk.length;
          if (text.length < 256 * 1024) text += chunk;
          if (text.includes(OPENAPI_MARKER) || received >= maxBytes) {
            res.destroy();
          }
        });
        res.on('close', () => {
          if (res.statusCode === 200 && text.includes(OPENAPI_MARKER)) {
            console.error(
              `[cip-dev-api] Port ${port} is occupied by a Channel Intelligence API (stale or duplicate uvicorn). ` +
                'Stopping it and starting a fresh instance.'
            );
            killProcessOnPort(port);
            setTimeout(() => resolve(null), 800);
            return;
          }
          if (res.statusCode === 200 && text.includes('"/api/v1/') && !text.includes(OPENAPI_MARKER)) {
            resolve(
              `[cip-dev-api] Port ${port} responds with OpenAPI JSON, but it does NOT list /api/v1/dev/database-wipe.\n` +
                `That almost always means a stale or foreign Python process is still bound to this port.\n` +
                `Stop the process and run pnpm dev:api again.`
            );
            return;
          }
          if (res.statusCode && res.statusCode !== 200 && received > 0) {
            resolve(
              `[cip-dev-api] Port ${port} returned HTTP ${res.statusCode} for /openapi.json — not the expected FastAPI app.\n` +
                `Free the port or pick another with CIP_API_PORT.`
            );
            return;
          }
          resolve(null);
        });
        res.on('error', () => resolve(null));
      }
    );

    req.on('error', (err) => {
      if (err.code === 'ECONNREFUSED') {
        resolve(null);
        return;
      }
      resolve(null);
    });
    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });
  });
}

(async () => {
  const portErr = await preflightListenPort();
  if (portErr) {
    console.error(portErr);
    process.exit(1);
  }

  const child = spawn(
    py,
    [
      '-m',
      'uvicorn',
      'app.main:app',
      '--reload',
      '--host',
      process.env.CIP_API_HOST || '0.0.0.0',
      '--port',
      process.env.CIP_API_PORT || '8001',
    ],
    { cwd: apiRoot, stdio: 'inherit', env: process.env }
  );

  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    process.exit(code ?? 1);
  });
})();
