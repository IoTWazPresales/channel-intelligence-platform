/**
 * Is the CIP always-on supervisor (scripts/cip-supervisor.ps1, N-0073) running?
 *
 * The supervisor owns the Celery worker. A manual `pnpm dev:worker` would kill its worker
 * (dev-worker.js stops every existing Celery process first) and the supervisor would then kill
 * the manual one, in a loop. dev-worker.js therefore refuses to start while the supervisor is live.
 *
 * Live = supervisor.pid names a running process AND status.json carries a heartbeat younger than
 * 10 minutes (the heartbeat guards against a reused PID after a crash). Processes the supervisor
 * starts itself carry CIP_SUPERVISOR_CHILD=1 and are always allowed.
 */
const fs = require('fs');
const path = require('path');

const HEARTBEAT_MAX_AGE_MS = 10 * 60 * 1000;

function supervisorStateDir(env = process.env) {
  if (!env.LOCALAPPDATA) return null;
  return path.join(env.LOCALAPPDATA, 'CIP', 'always-on');
}

function defaultIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return Boolean(e && e.code === 'EPERM');
  }
}

/**
 * @returns {number|null} the live supervisor PID, or null when it is not running (or this process is its child)
 */
function liveSupervisorPid({ env = process.env, now = Date.now(), isAlive = defaultIsAlive } = {}) {
  if (env.CIP_SUPERVISOR_CHILD === '1') return null;
  const dir = supervisorStateDir(env);
  if (!dir) return null;
  let pid;
  try {
    pid = parseInt(fs.readFileSync(path.join(dir, 'supervisor.pid'), 'utf8').trim(), 10);
  } catch {
    return null;
  }
  if (!Number.isFinite(pid) || pid <= 0 || !isAlive(pid)) return null;
  try {
    const raw = fs.readFileSync(path.join(dir, 'status.json'), 'utf8').replace(/^﻿/, '');
    const hb = Date.parse(JSON.parse(raw).supervisor.heartbeat);
    if (Number.isFinite(hb) && now - hb > HEARTBEAT_MAX_AGE_MS) return null;
  } catch {
    /* no readable status yet: a live PID is enough */
  }
  return pid;
}

module.exports = { liveSupervisorPid, supervisorStateDir, HEARTBEAT_MAX_AGE_MS };
