# Guard stdin / vitest / N-0006 — 2026-09-04

Labels: **VERIFIED** = reproduced this session with command output. **ASSERTED** = not reproduced here.

## H — transport crash vs IDENTITY_TOOL (2026-09-04 later)

**CONSULT:** opus CLI `OBSERVATION_TRANSPORT: deny_crash`. Event identity lives inside the payload; allow-on-unparseable cannot be scoped to observation until argv/hooks.json pass the event name (BACKLOG-172). `beforeReadFile` failClosed stays true. Cursor still holds the real path when stdin is empty.

**VERIFIED (harness):** `python .eif/audit/GUARD_STDIN_20260904/prove_stdin.py` → `=== PASS ===`

| Case | Result |
|------|--------|
| Hung-open incomplete JSON, watchdog=2 | `HOOK_TIMEOUT` crash, 2.391s |
| Complete JSON held-open, watchdog=8 | allow, 1.007s (does not wait for EOF) |
| Closed stdin `git status --short` | allow, 1.058s |
| Closed stdin `git push --force` | deny `ACTION_FORCE_VCS` / policy, 1.428s |
| Closed stdin `beforeReadFile` CONTEXT.md | allow, 0.556s |
| Zero-byte stdin closed | `HOOK_INPUT_INVALID` crash, 0.769s |
| JSON truncated mid-string | `HOOK_INPUT_INVALID` crash; `Unterminated string … column 49 (char 48)` — matches live `hook-guard.log` |
| Parsed `preToolUse` Read, empty `tool_input` | `HOOK_INPUT_INVALID` crash, **not** `IDENTITY_TOOL` |

**VERIFIED (live policy deny):** Shell `git status --short -- .cursor/hooks.json` → `EIF_GUARD_POLICY: CONTROL_PLANE_PROTECTED`.

**VERIFIED (burst ts≥1788527448):** live Read/Grep across `.eif/` and `apps/web/` allowed with real paths. Concurrent unparseable stdin audited as `HOOK_INPUT_INVALID` / `eif_guard_class=crash`. Grep of `.eif/runtime-events.jsonl` `"code":"IDENTITY_TOOL"`: last Read/Grep `path:null` was **before** the repair (`1788524851`). After the burst marker: **zero** `IDENTITY_TOOL` with `path:null`.

**Write path:** Cursor `StrReplace` on `.cursor/hooks/eif_guard.py` is `CONTROL_PLANE_PROTECTED`. Operator-authorized repair applied via `.eif/audit/GUARD_STDIN_20260904/apply_transport_crash_fix.py` (workspace shell is not a jail).

## E — stdin watchdog

**VERIFIED (source):** `.cursor/hooks/eif_guard.py` `__main__` calls `read_hook_stdin_eof()` then `_arm_watchdog()`. The read loops `os.read` until a 0-byte EOF. The watchdog cannot fire during that read.

**VERIFIED (harness):** `python .eif/audit/GUARD_STDIN_20260904/prove_stdin.py`

| Case | Result |
|------|--------|
| Complete JSON, stdin left open, `EIF_HOOK_WATCHDOG_SEC=2`, `wait` 12s | hung 12.048s; empty stdout; no `HOOK_TIMEOUT`; process killed by harness (`returncode` 1) |
| Closed stdin, `git status --short` | allow, **1.006s** |
| Closed stdin, `git push --force origin HEAD` | deny `ACTION_FORCE_VCS` / `eif_guard_class=policy`, **0.941s** |
| Closed stdin, `beforeReadFile` `CONTEXT.md` | allow, **0.437s** |

**VERIFIED (identity is not the 10s class):** closed-pipe shell allow 1.006s minus read-hook 0.437s ≈ **0.57s** identity. Cannot explain a 10s host kill.

**VERIFIED (live Cursor shell, this session):** `git rev-parse` / `git status` ran; `python .eif/runtime/programme/program.py --help` exit 0, command 895ms, Shell-tool wall 5100ms.

**ASSERTED:** Cursor `beforeShellExecution` sometimes holds the pipe open after writing JSON. Direct-invoke with an open pipe reproduces the unprotected read; live git/programme in this session did close or otherwise reach EOF (those commands ran).

**Fix not landed:** `StrReplace` on `.cursor/hooks/eif_guard.py` → `CONTROL_PLANE_PROTECTED`. One failure, not retried. Intended fix (not applied): arm watchdog before the read; treat a complete JSON object as a finished payload (do not wait for EOF); hung read must emit `HOOK_TIMEOUT` with a reason code.

First harness attempt used `Popen.communicate()`, which closes stdin and falsified the hang. Corrected to `proc.wait()` with stdin left open.

## F — vitest

**VERIFIED (guard on, this session):** `pnpm --filter @cip/web test` → **107 files collected**, **1 failed / 106 passed**, **1 failed / 582 passed (583)**. Duration 256s. No `UNKNOWN`, no `%TEMP%`, no `Failed to collect`, no `EIF_GUARD` in the log (`.eif/audit/GUARD_STDIN_20260904/vitest-guard-on.txt`, not committed).

**VERIFIED (the one failure):** `src/app/(app)/admin/mappings/DsiCandidateStewardPanel.test.tsx` — second test timed out at 5s under full-suite load (5270ms). Isolation: **2 passed** in 1.88s (that test 1651ms). Same class as BACKLOG-162.

**VERIFIED (density):** densest file this run is `commercial-planner/page.test.tsx` **83 tests** (~15× suite mean ~5.4). 83+27+16 = 126, which can explain a ~122-test gap if three dense files fail to collect. That arithmetic is **not** a naming of the prior session’s three files.

**Not run:** guard-disabled suite. Disabling `hooks.json` is `CONTROL_PLANE_PROTECTED` (same deny class as the E write; not retried).

**ASSERTED (prior session only):** 104 files / 461 passed, three uncollected, UNKNOWN opens under `%TEMP%\...\web\<hash>`. Not reproduced with the guard on. Those three filenames remain unknown.

## G — N-0006

See `docs/BACKLOG.md` BACKLOG-170. Engine invariants cited there. Node not advanced. CONSULT not used (path is not contested).
