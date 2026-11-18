// node --test scripts/run-api-fast-gate.test.cjs
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { readManifest, summarize, splitPhases } = require('./run-api-fast-gate.cjs');

const apiDir = path.resolve(__dirname, '..', 'apps', 'api');

test('the committed manifest lists existing paths once; the cip guard and unit tests run apart', () => {
  const paths = readManifest(path.join(apiDir, 'tests', 'fast_gate.txt'));
  assert.ok(paths.length >= 10);
  for (const p of paths) assert.ok(fs.existsSync(path.join(apiDir, p)), p);
  const { db, unit } = splitPhases(paths);
  assert.ok(db.includes('tests/test_conftest_cip_guard.py'));
  assert.deepStrictEqual(unit, ['tests/unit']);
});

test('unit paths go to the no-database run, in manifest order', () => {
  const { db, unit } = splitPhases(['tests/test_a.py', 'tests/unit/test_x.py', 'tests/unitish.py', 'tests/unit']);
  assert.deepStrictEqual(db, ['tests/test_a.py', 'tests/unitish.py']);
  assert.deepStrictEqual(unit, ['tests/unit/test_x.py', 'tests/unit']);
});

test('a duplicate manifest line is refused; comments and blanks are ignored', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'fastgate-'));
  const f = path.join(dir, 'm.txt');
  fs.writeFileSync(f, '# c\n\ntests/a.py\r\ntests/b.py\n');
  assert.deepStrictEqual(readManifest(f), ['tests/a.py', 'tests/b.py']);
  fs.writeFileSync(f, 'tests/a.py\ntests/a.py\n');
  assert.throws(() => readManifest(f), /twice/);
});

test('summary counts outcomes and sorts non-passing ids, with no timings', () => {
  const xml = `<testsuites><testsuite>
    <testcase classname="tests.test_z" name="test_b" time="1.2"><failure message="x">t</failure></testcase>
    <testcase classname="tests.test_a" name="test_a" time="0.1"/>
    <testcase classname="tests.test_a" name="test_err" time="0.3"><error message="e">t</error></testcase>
    <testcase classname="tests.test_a" name="test_skip" time="0"><skipped message="s"/></testcase>
  </testsuite></testsuites>`;
  const s = summarize(xml);
  assert.deepStrictEqual(s.counts, { passed: 1, failed: 1, error: 1, skipped: 1 });
  assert.strictEqual(s.total, 4);
  assert.deepStrictEqual(s.bad, ['ERROR tests.test_a::test_err', 'FAILED tests.test_z::test_b']);
  assert.ok(!s.bad.join('').includes('1.2'));
});