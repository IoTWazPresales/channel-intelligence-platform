const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { resolveApiBindHost, isLoopbackHost } = require('./api-bind-host.cjs');

test('default bind is IPv4 loopback', () => {
  assert.equal(resolveApiBindHost({}), '127.0.0.1');
  assert.equal(resolveApiBindHost({ CIP_API_HOST: '' }), '127.0.0.1');
  assert.equal(resolveApiBindHost({ CIP_API_HOST: '   ' }), '127.0.0.1');
});

test('explicit host is kept, including non-loopback', () => {
  assert.equal(resolveApiBindHost({ CIP_API_HOST: '0.0.0.0' }), '0.0.0.0');
  assert.equal(resolveApiBindHost({ CIP_API_HOST: '::1' }), '::1');
});

test('loopback classification', () => {
  assert.equal(isLoopbackHost('127.0.0.1'), true);
  assert.equal(isLoopbackHost('::1'), true);
  assert.equal(isLoopbackHost('localhost'), true);
  assert.equal(isLoopbackHost('0.0.0.0'), false);
});

test('dev-api.js does not default the listen host to 0.0.0.0', () => {
  const src = fs.readFileSync(path.join(__dirname, 'dev-api.js'), 'utf8');
  assert.equal(src.includes("|| '0.0.0.0'"), false);
  assert.equal(src.includes('resolveApiBindHost'), true);
});
