const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { liveSupervisorPid } = require('./supervisor-guard.cjs');

function stateDir(pid, heartbeatIso) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'cip-sup-guard-'));
  const dir = path.join(base, 'CIP', 'always-on');
  fs.mkdirSync(dir, { recursive: true });
  if (pid !== undefined) fs.writeFileSync(path.join(dir, 'supervisor.pid'), `${pid}\r\n`);
  if (heartbeatIso !== undefined) {
    // PowerShell may write a BOM; the guard must cope.
    fs.writeFileSync(path.join(dir, 'status.json'), '﻿' + JSON.stringify({ supervisor: { heartbeat: heartbeatIso } }));
  }
  return base;
}

const now = Date.parse('2026-10-07T12:00:00Z');
const alive = () => true;
const dead = () => false;

test('no state dir or pid file means not running', () => {
  assert.equal(liveSupervisorPid({ env: {}, now, isAlive: alive }), null);
  assert.equal(liveSupervisorPid({ env: { LOCALAPPDATA: stateDir() }, now, isAlive: alive }), null);
});

test('live pid with fresh heartbeat is running', () => {
  const env = { LOCALAPPDATA: stateDir(4242, '2026-10-07T11:59:30Z') };
  assert.equal(liveSupervisorPid({ env, now, isAlive: alive }), 4242);
});

test('dead pid is not running', () => {
  const env = { LOCALAPPDATA: stateDir(4242, '2026-10-07T11:59:30Z') };
  assert.equal(liveSupervisorPid({ env, now, isAlive: dead }), null);
});

test('stale heartbeat (reused pid after a crash) is not running', () => {
  const env = { LOCALAPPDATA: stateDir(4242, '2026-10-07T11:40:00Z') };
  assert.equal(liveSupervisorPid({ env, now, isAlive: alive }), null);
});

test('live pid without a status file yet counts as running', () => {
  const env = { LOCALAPPDATA: stateDir(4242) };
  assert.equal(liveSupervisorPid({ env, now, isAlive: alive }), 4242);
});

test("the supervisor's own children are allowed", () => {
  const env = { LOCALAPPDATA: stateDir(4242, '2026-10-07T11:59:30Z'), CIP_SUPERVISOR_CHILD: '1' };
  assert.equal(liveSupervisorPid({ env, now, isAlive: alive }), null);
});

test('dev-worker.js consults the guard before it stops any Celery process', () => {
  const src = fs.readFileSync(path.join(__dirname, 'dev-worker.js'), 'utf8');
  const guardAt = src.indexOf('liveSupervisorPid(');
  assert.ok(guardAt > 0, 'dev-worker.js must call liveSupervisorPid');
  assert.ok(guardAt < src.indexOf('killStaleCeleryWorkers();'), 'guard must run before the stale-worker kill');
});
