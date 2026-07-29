#!/usr/bin/env node

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = process.cwd();
const git = process.platform === "win32" ? "git.exe" : "git";
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const python = process.platform === "win32" ? "python.exe" : "python3";
const failures = [];
const warnings = [];
const notes = [];

function run(command, args, cwd = root) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    windowsHide: true,
    shell: false,
  });
  return {
    status: result.status === null ? 1 : result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    error: result.error,
  };
}

function gitRun(args, cwd = root) {
  return run(git, args, cwd);
}

function die(message) {
  console.error(`verify-gate: ${message}`);
  process.exit(2);
}

function parseArgs(argv) {
  const options = {
    base: null,
    head: "HEAD",
    expectedBase: null,
    testFiles: [],
    tscBaseList: null,
    tscHeadList: null,
    skipTsc: false,
    skipTests: false,
    skipProhibited: false,
    skipBase: false,
    allowBranchesAhead: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--skip-tsc") options.skipTsc = true;
    else if (arg === "--skip-tests") options.skipTests = true;
    else if (arg === "--skip-prohibited") options.skipProhibited = true;
    else if (arg === "--skip-base") options.skipBase = true;
    else if (arg === "--allow-branches-ahead") options.allowBranchesAhead = true;
    else if (
      arg === "--base" ||
      arg === "--head" ||
      arg === "--expected-base" ||
      arg === "--test-files" ||
      arg === "--tsc-base-list" ||
      arg === "--tsc-head-list"
    ) {
      const value = argv[++i];
      if (!value || value.startsWith("--")) die(`${arg} requires a value`);
      if (arg === "--base") options.base = value;
      else if (arg === "--head") options.head = value;
      else if (arg === "--expected-base") options.expectedBase = value;
      else if (arg === "--test-files") options.testFiles.push(value);
      else if (arg === "--tsc-base-list") options.tscBaseList = value;
      else options.tscHeadList = value;
    } else {
      die(`unknown argument: ${arg}`);
    }
  }
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/verify-gate.cjs [--base <ref>] [--head <ref>] [--expected-base <sha>]
    [--test-files <path>] [--skip-tsc] [--skip-tests] [--skip-prohibited] [--skip-base]
    [--allow-branches-ahead] [--tsc-base-list <file>] [--tsc-head-list <file>]

Defaults: --base origin/main (fallback main), --head HEAD.

Checks TypeScript error-list regressions, matched test files, prohibited
import-steward filenames, and base/branch integrity.`);
}

function resolveRef(ref, fallback) {
  const direct = gitRun(["rev-parse", "--verify", `${ref}^{commit}`]);
  if (direct.status === 0) return direct.stdout.trim();
  const alternate = gitRun(["rev-parse", "--verify", `${fallback}^{commit}`]);
  if (alternate.status === 0) return alternate.stdout.trim();
  die(`cannot resolve git ref ${ref}${fallback ? ` or fallback ${fallback}` : ""}`);
}

function normalizeErrorList(text) {
  const keys = new Set();
  const expression = /^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):/gm;
  let match;
  while ((match = expression.exec(text)) !== null) {
    const file = match[1].replaceAll("\\", "/").trim();
    keys.add(`${file}|${match[4]}`);
  }
  return keys;
}

function readErrorList(file) {
  try {
    return normalizeErrorList(fs.readFileSync(path.resolve(root, file), "utf8"));
  } catch (error) {
    failures.push(`cannot read tsc list ${file}: ${error.message}`);
    return new Set();
  }
}

function formatSet(set) {
  return [...set].sort().join("\n");
}

function runTsc(cwd) {
  const result = run(pnpm, ["--filter", "@cip/web", "exec", "tsc", "--noEmit"], cwd);
  return { ...result, text: `${result.stdout}\n${result.stderr}` };
}

function symlinkNodeModules(worktree) {
  const source = path.join(root, "node_modules");
  const target = path.join(worktree, "node_modules");
  if (!fs.existsSync(source) || fs.existsSync(target)) return;
  try {
    fs.symlinkSync(source, target, process.platform === "win32" ? "junction" : "dir");
  } catch (error) {
    warnings.push(`could not link node_modules into base worktree: ${error.message}`);
  }
}

function makeBaseWorktree(baseSha) {
  const worktree = fs.mkdtempSync(path.join(os.tmpdir(), "cip-verify-gate-"));
  const added = gitRun(["worktree", "add", "--detach", worktree, baseSha]);
  if (added.status !== 0) {
    fs.rmSync(worktree, { recursive: true, force: true });
    failures.push(`could not create base worktree: ${added.stderr.trim()}`);
    return null;
  }
  symlinkNodeModules(worktree);
  return worktree;
}

function removeBaseWorktree(worktree) {
  if (!worktree) return;
  const linkedModules = path.join(worktree, "node_modules");
  try {
    if (fs.lstatSync(linkedModules).isSymbolicLink()) fs.unlinkSync(linkedModules);
  } catch (error) {
    if (error.code !== "ENOENT") warnings.push(`could not unlink temporary node_modules junction: ${error.message}`);
  }
  const removed = gitRun(["worktree", "remove", "--force", worktree]);
  if (removed.status !== 0) {
    warnings.push(`could not remove temporary base worktree: ${removed.stderr.trim()}`);
    fs.rmSync(worktree, { recursive: true, force: true });
  }
}

function parseTestSummary(text, runner) {
  const summary = { passed: 0, failed: 0, skipped: 0 };
  const patterns =
    runner === "pytest"
      ? [
          [/(\d+)\s+passed\b/i, "passed"],
          [/(\d+)\s+failed\b/i, "failed"],
          [/(\d+)\s+(?:skipped|xfailed)\b/i, "skipped"],
        ]
      : [
          [/(\d+)\s+passed\b/i, "passed"],
          [/(\d+)\s+failed\b/i, "failed"],
          [/(\d+)\s+skipped\b/i, "skipped"],
        ];
  for (const [pattern, field] of patterns) {
    const match = text.match(pattern);
    if (match) summary[field] = Number(match[1]);
  }
  return summary;
}

function runnerFor(files) {
  if (files.some((file) => file.replaceAll("\\", "/").startsWith("apps/api/tests/"))) {
    return "pytest";
  }
  return "vitest";
}

function normalizeTestFiles(values) {
  return [...new Set(values.flatMap((value) => value.split(",").map((item) => item.trim()).filter(Boolean)))].map(
    (file) => file.replaceAll("\\", "/"),
  );
}

function runTests(cwd, files, runner) {
  if (runner === "pytest") {
    return run(python, ["-m", "pytest", ...files], cwd);
  }
  return run(pnpm, ["--filter", "@cip/web", "exec", "vitest", "run", ...files], cwd);
}

function testCheck(options, baseSha) {
  const files = normalizeTestFiles(options.testFiles);
  if (files.length === 0) {
    notes.push("tests: SKIP (no --test-files supplied)");
    return;
  }
  const runner = runnerFor(files);
  const baseWorktree = makeBaseWorktree(baseSha);
  if (!baseWorktree) return;
  try {
    const missingBase = files.filter((file) => !fs.existsSync(path.join(baseWorktree, file)));
    const missingHead = files.filter((file) => !fs.existsSync(path.join(root, file)));
    if (missingBase.length || missingHead.length) {
      failures.push(
        `tests: explicitly listed set is not present at both refs (base missing: ${missingBase.join(", ") || "none"}; head missing: ${missingHead.join(", ") || "none"})`,
      );
      return;
    }
    const base = runTests(baseWorktree, files, runner);
    const head = runTests(root, files, runner);
    const baseSummary = parseTestSummary(`${base.stdout}\n${base.stderr}`, runner);
    const headSummary = parseTestSummary(`${head.stdout}\n${head.stderr}`, runner);
    console.log(
      `tests: ${runner}, identical files=${files.length}, base ${baseSummary.passed} passed/${baseSummary.failed} failed/${baseSummary.skipped} skipped, head ${headSummary.passed} passed/${headSummary.failed} failed/${headSummary.skipped} skipped`,
    );
    if (head.status !== 0 && base.status === 0) {
      failures.push("tests: HEAD failed while BASE passed");
    } else if (headSummary.failed > baseSummary.failed || headSummary.passed < baseSummary.passed) {
      failures.push("tests: HEAD has a regression in pass/fail counts");
    } else if (headSummary.skipped > baseSummary.skipped) {
      failures.push("tests: HEAD skips more tests than BASE");
    }
    if (head.status !== 0 && base.status !== 0 && headSummary.failed > baseSummary.failed) {
      failures.push("tests: HEAD introduces additional failures over BASE");
    }
  } finally {
    removeBaseWorktree(baseWorktree);
  }
}

function prohibitedCheck(base, head, options) {
  const target = path.join(root, "apps", "web", "src", "features", "import-steward");
  const offenders = [];
  if (fs.existsSync(target)) {
    const stack = [target];
    while (stack.length) {
      const current = stack.pop();
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) stack.push(full);
        else if (/^(Dsi|Shipment|Cpor)/.test(entry.name)) offenders.push(path.relative(root, full));
      }
    }
  }
  if (offenders.length) failures.push(`prohibited: importer-prefixed files found:\n  ${offenders.join("\n  ")}`);
  const diff = gitRun(["diff", "--name-status", `${base}..${head}`]);
  if (diff.status === 0) {
    const added = diff.stdout
      .split(/\r?\n/)
      .filter((line) => line.startsWith("A\t") || line.startsWith("R"))
      .map((line) => line.split("\t").at(-1))
      .filter((file) => /(^|\/)apps\/web\/src\/features\/import-steward\/(Dsi|Shipment|Cpor)/.test(file));
    if (added.length) failures.push(`prohibited: diff adds importer-prefixed files:\n  ${added.join("\n  ")}`);
  }
  const scriptDiff = gitRun(["diff", "--", "scripts/verify-gate.cjs"]);
  if (scriptDiff.stdout.includes("git add -A") || scriptDiff.stdout.includes("git add .")) {
    failures.push("prohibited: verify-gate script contains a forbidden broad git add");
  }
}

function reflogCheck(headSha) {
  const refsResult = gitRun(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"]);
  if (refsResult.status !== 0) {
    warnings.push("base: unable to enumerate refs for reflog reset scan");
    return;
  }
  let suspicious = 0;
  for (const ref of refsResult.stdout.split(/\r?\n/).filter(Boolean).concat(["HEAD"])) {
    const log = gitRun(["reflog", "show", "--format=%H%x09%gs", ref]);
    if (log.status !== 0) continue;
    const entries = log.stdout.split(/\r?\n/).filter(Boolean).map((line) => {
      const [sha, ...subject] = line.split("\t");
      return { sha, subject: subject.join("\t") };
    });
    entries.forEach((entry, index) => {
      if (!/\breset:\s+moving to\b/i.test(entry.subject)) return;
      const oldSha = entries[index + 1]?.sha;
      if (!oldSha) {
        warnings.push(`base: reset scan could not identify the prior commit for ${ref}`);
        return;
      }
      const reachable = gitRun(["merge-base", "--is-ancestor", oldSha, headSha]);
      if (reachable.status !== 0) {
        suspicious += 1;
        failures.push(`base: hard reset on ${ref} discarded unreachable commit ${oldSha.slice(0, 12)}`);
      }
    });
  }
  if (!suspicious) notes.push("base: reflog reset scan found no clear discarded commits");
}

function branchesAheadCheck(headRef, allow) {
  const mainRef = resolveRef("origin/main", "main") ? "origin/main" : "main";
  const mainSha = resolveRef(mainRef, "main");
  const refsResult = gitRun(["for-each-ref", "--format=%(refname:short)\t%(objectname)", "refs/heads", "refs/remotes"]);
  if (refsResult.status !== 0) {
    failures.push("base: could not enumerate local and remote-tracking branches");
    return;
  }
  const headBranch = gitRun(["symbolic-ref", "--quiet", "--short", headRef]).stdout.trim();
  const excludedRefs = new Set([headBranch, headRef, "main", mainRef]);
  if (headBranch) excludedRefs.add(`origin/${headBranch}`);
  const seenShas = new Set();
  const ahead = [];
  for (const line of refsResult.stdout.split(/\r?\n/).filter(Boolean)) {
    const [name, sha] = line.split("\t");
    if (!name || !sha || name === "origin/HEAD" || excludedRefs.has(name)) continue;
    if (seenShas.has(sha)) continue;
    const merged = gitRun(["merge-base", "--is-ancestor", sha, mainSha]);
    if (merged.status !== 0) {
      seenShas.add(sha);
      ahead.push(`${name} (${sha.slice(0, 12)})`);
    }
  }
  if (ahead.length) {
    const message = `base: branches ahead of ${mainRef}:\n  ${ahead.join("\n  ")}`;
    if (allow) warnings.push(`${message}\n  allowed by --allow-branches-ahead`);
    else failures.push(message);
  } else {
    notes.push(`base: no other branches ahead of ${mainRef}`);
  }
}

function baseCheck(options, base, head, baseSha, headSha) {
  const mergeBase = gitRun(["merge-base", base, head]);
  if (mergeBase.status !== 0) {
    failures.push(`base: cannot calculate merge-base for ${base} and ${head}`);
  } else {
    const actual = mergeBase.stdout.trim();
    console.log(`base: merge-base=${actual}`);
    if (options.expectedBase && actual !== resolveRef(options.expectedBase)) {
      failures.push(`base: merge-base ${actual} does not match --expected-base ${options.expectedBase}`);
    }
  }
  reflogCheck(headSha);
  branchesAheadCheck(options.head, options.allowBranchesAhead);
}

function tscCheck(options, baseSha) {
  if (options.tscBaseList || options.tscHeadList) {
    if (!options.tscBaseList || !options.tscHeadList) {
      failures.push("tsc: --tsc-base-list and --tsc-head-list must be supplied together");
      return;
    }
    compareTsc(readErrorList(options.tscBaseList), readErrorList(options.tscHeadList), "pre-captured");
    return;
  }
  const baseWorktree = makeBaseWorktree(baseSha);
  if (!baseWorktree) return;
  try {
    const base = runTsc(baseWorktree);
    const head = runTsc(root);
    compareTsc(normalizeErrorList(base.text), normalizeErrorList(head.text), "live");
  } finally {
    removeBaseWorktree(baseWorktree);
  }
}

function compareTsc(baseErrors, headErrors, source) {
  const newErrors = [...headErrors].filter((key) => !baseErrors.has(key)).sort();
  console.log(`tsc: ${source}, BASE errors=${baseErrors.size}, HEAD errors=${headErrors.size}, NEW=${newErrors.length}`);
  if (newErrors.length) failures.push(`tsc: HEAD introduces new errors:\n  ${newErrors.join("\n  ")}`);
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }
  const base = options.base || (resolveRef("origin/main", "main") ? "origin/main" : "main");
  const baseSha = resolveRef(base, "main");
  const headSha = resolveRef(options.head, null);
  console.log(`verify-gate: base=${base} (${baseSha.slice(0, 12)}), head=${options.head} (${headSha.slice(0, 12)})`);
  if (!options.skipTsc) tscCheck(options, baseSha);
  else notes.push("tsc: SKIP");
  if (!options.skipTests) testCheck(options, baseSha);
  else notes.push("tests: SKIP");
  if (!options.skipProhibited) prohibitedCheck(baseSha, headSha, options);
  else notes.push("prohibited: SKIP");
  if (!options.skipBase) baseCheck(options, base, options.head, baseSha, headSha);
  else notes.push("base: SKIP");
  for (const note of notes) console.log(`verify-gate: ${note}`);
  for (const warning of warnings) console.warn(`verify-gate WARNING: ${warning}`);
  if (failures.length) {
    console.error(`verify-gate FAILED (${failures.length} check${failures.length === 1 ? "" : "s"}):`);
    for (const failure of failures) console.error(`- ${failure}`);
    process.exitCode = 1;
  } else {
    console.log("verify-gate PASSED");
  }
}

main();
