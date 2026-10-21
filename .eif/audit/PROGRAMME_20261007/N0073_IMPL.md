# N-0073 implementation run RUN-20261007-N0073-IMPL (2026-10-07)

Lenses: platform-devops-engineer (owner), test-engineering-specialist, reliability-sre-specialist.
Built against N0073_DESIGN.md. Risk R2, facet infra. This is the implementation run's own self-check; GOV-008 verification still has to be done by a separate run.
A usage limit cut off the first session partway through validation. This file covers both sessions: the build (first session) and the fixes plus measurements (continuation, 14:40-15:08 local SAST). The lease was re-acquired at ledger rev 1550, with the node at revision 7 and stage `implement`.

**Status: the supervisor is RUNNING** (pid 46156, hidden, started the same way as the Startup shortcut). All 6 components are healthy. The public link is `https://build-ebooks-heading-scoring.trycloudflare.com/login` (quick tunnel: the address changes whenever cloudflared restarts).

## Files changed

| File | State | What |
|---|---|---|
| `scripts/cip-supervisor.ps1` | new (untracked) | The check loop (design §Loop/Components/Tunnel). Changed in this session: (a) orphaned-listener handling: `Get-OrphanRoots`, `Resolve-PortOwner`, `Get-ApiChildMatch`, `$WebChildMatch`; `Stop-Tree` stops a dead root's matching children and leaves a reused PID alone (`-RootStart`); `Set-Adopted` logs only when the PID changes. (b) `Write-TextFile` swaps the file with `MoveFileEx(REPLACE_EXISTING|WRITE_THROUGH)` and falls back to `File.Replace`; it no longer uses `Move-Item -Force`. (c) Worker: `@($workers) + @($beats)`, and Celery orphans of a dead wrapper are stopped before the restart. |
| `scripts/cip-supervisor-install.ps1` | new | Startup shortcut and desktop shortcuts. Added a read-only `-Check` switch in this session. |
| `scripts/cip-supervisor-stop.ps1` | new | Writes stop.flag. `-Component x`, `-Restart`. Unchanged in this session. |
| `scripts/cip-supervisor-status.ps1` | new (this session) | Prints status.json, the listeners (`-Ports`) plus a Redis PING, local codes (`-Local`), public codes built from the status.json hostname (`-Public`), and log tails (`-Log N -LogFile x`). |
| `scripts/supervisor-guard.cjs` and `.test.cjs` | new | Is the supervisor live (pid plus a heartbeat under 10 min). Used by dev-worker.js. |
| `scripts/dev-worker.js` | modified | Refuses to start while the supervisor is live. Passes `-s $CIP_CELERY_BEAT_SCHEDULE` to beat. |
| `scripts/restart-dev.ps1` | modified | Refuses while the supervisor is live. |
| `scripts/pilot-tunnel.ps1` | untracked | The hostname comes from `/quicktunnel` JSON (`.hostname`). There is no regex, and the auth gates are kept (session mode, API 401, web 200, proxy 401). This was already done when the continuation started, and I confirmed it. |
| `apps/web/package.json` | modified | `start` = `next start -H 127.0.0.1 -p 3000`. |
| `.gitignore` | modified (this session) | `celerybeat-schedule*`, with a comment. |
| `scripts/api-bind-host.cjs` and `.test.cjs`, `scripts/dev-api.js` | in the working tree | Loopback default for `pnpm dev:api`. This is not in the N-0073 design, and this session did not establish who wrote it. Its tests were run because the brief asked for them. |

Audit-only helpers (not product): `N0073_static.ps1` (parse checks plus orphan and swap logic tests with fakes), `N0073_swap_probe.ps1`, `N0073_killtest.ps1`, `N0073_waithealthy.ps1`, `N0073_probe.ps1`, `N0073_fn_probe.ps1`.

## Findings and fixes in this session

1. **Orphaned API listener (FACT).** Port 8001 was attributed to pid 19756, which no longer existed. The live server was pid 39224, whose command line is `...spawn_main(parent_pid=19756, pipe_handle=820) --multiprocessing-fork`: the uvicorn `--reload` child of an earlier `pnpm dev:api`. It does **not** contain `uvicorn app.main`, so the API match also accepts `spawn_main(parent_pid=<dead owner>,`. The old supervisor re-adopted the dead PID on every cycle and wrote "api: adopted running process 19756" every 33 s (about 100 lines). After the fix, the new supervisor adopted 39224 once (14:57:26) and the repeated line stopped.
2. **The status write had a gap (MEASURED).** `N0073_swap_probe.ps1` rewrote the file 300 times while a busy reader read it. `Move-Item -Force` left the reader without a file 101 times. `File.Replace` left it without a file 89 times and caused 208 sharing errors, so it is **not** gap-free on this machine (the brief suggested it). `MoveFileEx` left it without a file 0 times. MoveFileEx is refused (error 5) while a reader holds the file open, so `Write-TextFile` falls back to `File.Replace` on that attempt and retries 5 times. In `N0073_static.ps1` (300 rewrites with a reader checking existence): 0 missing, 0 write failures, and replacing while a reader holds the file works. Passing a plain `$null` as the backup argument fails in PS 5.1 ("path is not of a legal form"); `[NullString]::Value` is required.
3. **Redis was not down (FACT).** `service redis-server status` reports active (running) since 13:53:07 SAST and `redis-cli ping` returns PONG. 6379 is missing from the Windows listener table (`Get-NetTCPConnection`) because WSL2 localhost forwarding does not show up there. That table was the source of the "not listening" observation. Nothing needed fixing; `cip-supervisor-status.ps1 -Ports` now PINGs Redis directly.
4. **Earlier failure in the log (FACT, already fixed before this session).** The first supervisor (pid 16524, 14:00) logged `worker= beat=` (blank counts) and `op_Addition on CimInstance`. That copy then killed its first worker (14:02:24) and restarted the web once (14:03:30) while both were healthy. Cause: in PS 5.1 a function's one-element return is unwrapped to a bare CimInstance, and `.Count` on it is blank. This was reproduced in this session: `F` returns `.Count` = "" and `@(F)` returns 1. Every current call site wraps with `@()`, and the `+` is now `@()+@()`.
5. **Beat schedule (FACT).** `CIP_CELERY_BEAT_SCHEDULE` is honoured. The live beat command line is `celery -A app.worker.celery_app beat -l info -s <LOCALAPPDATA>\CIP\always-on\celerybeat-schedule`, which is outside the repo. The three tracked files `apps/api/celerybeat-schedule.{bak,dat,dir}` are unmodified (`git status` is clean for them). Their July timestamps mean a manual run wrote them earlier. The `.gitignore` line does not untrack them.
6. **Tasks waiting in Redis (OBSERVATION).** The worker first started under the supervisor at 14:00:19, in the earlier session and before this check could run. Its log (`worker.err.log.1`) shows no task received between "ready" at 14:00:45 and the first beat-sent task at 14:01:43, so the queue was empty or close to it. Now: `LLEN celery` / `interactive` / `batch` in db 1 = 0 / 0 / 0, both before the restart and at the end. The worker was not held.

## Commands and results

| Command | Result |
|---|---|
| `python .eif/runtime/programme/program.py ... event node.lease.acquire` (rev 7, ttl 7200) | rev 1550 |
| `powershell -File .eif/audit/PROGRAMME_20261007/N0073_static.ps1` | Parse: 0 errors in `cip-supervisor.ps1`, `-install`, `-stop`, `-status`, `pilot-tunnel.ps1`, `restart-dev.ps1`. 11/11 logic checks PASS. Live check: port 8001 owner 19756 (dead) is served by 39224; port 3000 owner 41552 is alive and serves itself. |
| `node --test scripts/supervisor-guard.test.cjs scripts/api-bind-host.test.cjs` | 11 pass, 0 fail |
| `node --check` on dev-worker.js, supervisor-guard.cjs, dev-api.js, api-bind-host.cjs | exit 0 |
| `wsl -d Ubuntu -u root -- redis-cli -n 1 LLEN celery/interactive/batch` | 0 / 0 / 0 |
| `scripts/cip-supervisor-stop.ps1 -Restart` | Old supervisor 28544 stopped in 1 s. It stopped the web it owned (41552) and the tunnel (40368), and left the adopted worker and API alone. New supervisor 46156 started 14:57:22. |
| Second copy: `powershell -File scripts/cip-supervisor.ps1` while 46156 runs | Exited in 1.8 s with code 0. Log: "[pid 31840] another supervisor is already running; exiting." |
| `node scripts/dev-worker.js` while the supervisor runs | Refused with exit 1: "The CIP always-on supervisor (pid 46156) is running ..." |
| `scripts/cip-supervisor-install.ps1 -Check` | Exit 0. The Startup shortcut `...\Startup\CIP always-on.lnk` runs `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "<repo>\scripts\cip-supervisor.ps1"` with window style 7. Desktop shortcuts `CIP status.url` (file:///.../link.html) and `CIP public link.url` (the current link) are both present. The Desktop folder is under OneDrive. |
| Log scan for `not written`, `cycle N error`, `stop.flag error` | Only the 14:02:24 entry from the old copy (finding 4). None since the restart. |

## Measurements

The supervisor checks every 30 s. Time-to-healthy runs from the kill to the moment status.json shows `healthy` for a new launch. Detection takes up to one cycle and confirmation one more.

| Event | Detected | Restarted | Healthy | Time to healthy |
|---|---|---|---|---|
| Supervisor restart (stop to every component healthy) | - | 14:57:22 | 14:58:25 | 67 s (web and tunnel were relaunched; worker, API, WSL and Redis were adopted) |
| Kill web (pid 48012) | 14:59:35 | 14:59:36 (pid 29104) | 15:00:10 | **55 s** |
| Kill API (pid 39224, the adopted orphan) | 15:00:46 | 15:00:47 (pid 23248, supervisor-owned, no --reload) | 15:01:21 | **53 s** |
| Kill worker wrapper (node pid 31600) | 15:01:55 (no Celery orphans left) | 15:01:56 (pid 27436) | 15:02:28 (worker=1, beat=1) | **46 s** |
| Redis `service redis-server stop` | 15:03:36 (1/2 fail; worker set to waiting) | 15:04:10 (service start) | 15:04:11 (worker healthy again) | **51 s** |
| Kill cloudflared (pid 34196), last | 15:04:45 | 15:04:46 (pid 27468) | 15:05:28; new link at 15:04:54 | **56 s**; public 200/401 confirmed at 15:05:31 |

| Check (end state, 15:07:29) | Result |
|---|---|
| All components in status.json | wsl, redis, worker, api, web, tunnel: all `healthy`, cycle 17 |
| Web bind | Only `127.0.0.1:3000` (pid 29104). There is no 0.0.0.0 or :: listener. |
| API bind | `127.0.0.1:8001` (pid 10020, the real interpreter under the venv launcher 23248) |
| Local | API /health 200, API /auth/me 401, web /login 200, web proxy /auth/me 401 |
| Public, after the tunnel kill | `https://build-ebooks-heading-scoring.trycloudflare.com/login` **200**, `/api/v1/auth/me` **401**. The supervisor's own check at 15:06:01 matches. |
| Public, before the tunnel kill (after the restart) | `https://realized-quickly-engineering-tue.trycloudflare.com` /login 200, /auth/me 401 |
| CIP_LISTING_LIVE_FETCH / CIP_LISTING_CAPTURE_SCHEDULE | Not present in the supervisor's environment |

## Open items

1. **Leftover tasks (operator).** These could not be listed before the very first worker start because the earlier session had already started it. Indirect evidence says the queue was empty (finding 6), and it is now 0. Design question 4 is therefore moot for this run.
2. **The earlier session restarted things it should have adopted.** That was finding 4, an old bug that is now fixed. For GOV-008 to re-check: the current code adopts healthy processes (shown 14:57:23-26 for worker, API and WSL).
3. **The tracked `apps/api/celerybeat-schedule.{bak,dat,dir}` files** stay tracked. Untracking them needs `git rm --cached`, which is outside this run's write scope.
4. **`scripts/api-bind-host.cjs` and the `dev-api.js` change** have no N-0073 design entry. Their origin should be confirmed before commit.
5. **Design questions 1-3 remain the operator's.** Q1: beat is on and does write scheduled rows. Since 15:02 these ran: reaper, `listing_capture.poll_listings` (a gated no-op) and `reports.run_due_schedules` (due_count 0 at 14:01). Q2: API restart after a code change (`-Component api -Restart`). Q3: keep-awake. The API now runs supervisor-owned **without --reload**.
6. **Quick tunnel.** The address changes on every cloudflared restart, supervisor restart or reboot. The desktop `CIP public link.url` follows it. A named tunnel is N-0074.
7. **Detection latency** is one to two 30 s cycles, so recovery took 46-56 s. That meets the "check at least every 60 s" criterion.
8. **Not verified independently.** GOV-008 must run under a different `--run`.

## Quality facets (as recorded)
- reliability: pass. Every component was killed once and came back in 46-56 s, the mutex was shown, the supervisor was restarted cleanly, and it is left running.
- observability: pass. status.json carries the heartbeat, states, PIDs, adopted flags, launches and link; link.html has a stale warning; the supervisor and component logs rotate; the status script was added; the swap gap was measured at 0.
- finops: pass. Zero spend: Cloudflare quick tunnel (free, no account), local processes only, no cloud resources.
