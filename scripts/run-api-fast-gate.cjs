// Fast API gate (Wave 3 B1). Runs the fixed subset in apps/api/tests/fast_gate.txt, in file order:
// database paths first (one pytest process on the CI database), then tests/unit paths in a second
// process with CIP_UNIT_TESTS_FORBID_DB=1. Stable outputs: .tmp/api-fast-gate.txt (pytest logs),
// .tmp/api-fast-junit.xml and .tmp/api-fast-unit-junit.xml, and
// .tmp/api-fast-summary.txt (counts and sorted non-passing test ids, no timings), so two runs of the
// same code give the same summary. Exit code is 0 only when both runs pass; a missing manifest path
// fails before pytest.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const apiDir = path.join(root, 'apps', 'api');
const outDir = path.join(root, '.tmp');

function readManifest(file) {
  const seen = new Set();
  const paths = [];
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (seen.has(line)) throw new Error(`fast_gate.txt lists ${line} twice`);
    seen.add(line);
    paths.push(line);
  }
  return paths;
}

function summarize(junitXml) {
  const cases = [...junitXml.matchAll(/<testcase\b([^>]*?)(\/>|>([\s\S]*?)<\/testcase>)/g)];
  const counts = { passed: 0, failed: 0, error: 0, skipped: 0 };
  const bad = [];
  for (const m of cases) {
    const attrs = m[1];
    const body = m[3] || '';
    const cls = (attrs.match(/classname="([^"]*)"/) || [])[1] || '';
    const name = (attrs.match(/\bname="([^"]*)"/) || [])[1] || '';
    const id = `${cls}::${name}`;
    if (/<failure\b/.test(body)) { counts.failed++; bad.push(`FAILED ${id}`); }
    else if (/<error\b/.test(body)) { counts.error++; bad.push(`ERROR ${id}`); }
    else if (/<skipped\b/.test(body)) { counts.skipped++; }
    else counts.passed++;
  }
  bad.sort();
  return { counts, bad, total: cases.length };
}

function isUnit(p) {
  return p === 'tests/unit' || p.startsWith('tests/unit/');
}

function splitPhases(paths) {
  return { db: paths.filter((p) => !isUnit(p)), unit: paths.filter(isUnit) };
}

function main() {
  const manifest = path.join(apiDir, 'tests', 'fast_gate.txt');
  const paths = readManifest(manifest);
  const missing = paths.filter((p) => !fs.existsSync(path.join(apiDir, p)));
  if (missing.length) {
    console.error(`fast_gate.txt lists paths that do not exist: ${missing.join(', ')}`);
    process.exit(2);
  }
  fs.mkdirSync(outDir, { recursive: true });
  const venv = process.platform === 'win32'
    ? path.join(apiDir, '.venv', 'Scripts', 'python.exe')
    : path.join(apiDir, '.venv', 'bin', 'python3');
  const py = process.env.PYTHON || (fs.existsSync(venv) ? venv : (process.platform === 'win32' ? 'python' : 'python3'));
  const phases = splitPhases(paths);
  const runs = [
    { label: 'database subset', paths: phases.db, junit: path.join(outDir, 'api-fast-junit.xml'), env: {} },
    { label: 'unit (no database)', paths: phases.unit, junit: path.join(outDir, 'api-fast-unit-junit.xml'),
      env: { CIP_UNIT_TESTS_FORBID_DB: '1' } },
  ].filter((x) => x.paths.length);
  let log = '';
  let summary = `fast API gate\nmanifest: ${paths.length} paths\n`;
  let status = 0;
  for (const run of runs) {
    fs.rmSync(run.junit, { force: true });
    const args = ['-m', 'pytest', ...run.paths, '-q', '-p', 'no:cacheprovider', '-rfE', `--junitxml=${run.junit}`];
    const r = spawnSync(py, args, {
      cwd: apiDir, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, shell: process.platform === 'win32',
      env: { ...process.env, ...run.env },
    });
    const out = (r.stdout || '') + (r.stderr || '');
    process.stdout.write(out);
    log += `==== ${run.label} ====\n${out}\n`;
    const code = r.status ?? 1;
    if (code !== 0) status = 1;
    summary += `${run.label}: pytest exit ${code}\n`;
    if (fs.existsSync(run.junit)) {
      const s = summarize(fs.readFileSync(run.junit, 'utf8'));
      summary += `  tests: ${s.total} passed: ${s.counts.passed} failed: ${s.counts.failed} errors: ${s.counts.error} skipped: ${s.counts.skipped}\n`;
      summary += s.bad.length ? `${s.bad.map((b) => `  ${b}`).join('\n')}\n` : '  no failures\n';
    } else {
      summary += '  no junit report written\n';
    }
  }
  fs.writeFileSync(path.join(outDir, 'api-fast-gate.txt'), log);
  fs.writeFileSync(path.join(outDir, 'api-fast-summary.txt'), summary);
  console.log(`\n${summary}`);
  process.exit(status);
}

if (require.main === module) main();
module.exports = { readManifest, summarize, splitPhases };