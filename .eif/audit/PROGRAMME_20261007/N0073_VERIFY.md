# N-0073 GOV-008 verification, run RUN-20261007-N0073-VER (2026-10-07)

Node N-0073 (always-on supervisor), class feature, risk R2, facet infra, ledger revision 13 at the start, stage `validate`, no lease held.
Implementation run: RUN-20261007-N0073-IMPL. This run: RUN-20261007-N0073-VER.
Lenses: verification-controller (GOV-008), reliability-sre-specialist, application-security-specialist.

**Independence rung: R2, a fresh-context subagent of the same model family.** This is not a different model. I re-executed the checks below and did not rely on N0073_IMPL.md except where a row says so. The `Skill` tool is blocked in this session (adapter fault SHIM_TOOL_UNMAPPED), so I read the verification-controller SKILL.md directly.

**Overall verdict: VERIFIED_WITH_LIMITATIONS.** Every criterion I re-executed passed and none failed. The limitations are listed under each criterion and collected at the end. The main ones: I killed only web and the worker wrapper, not the API, Redis, WSL or cloudflared, and I did not run a cold start from nothing.

## Re-executed evidence

| # | Command (this run) | Observed |
|---|---|---|
| E1 | `scripts/cip-supervisor-status.ps1 -Ports -Local -Public -Log 30` (15:18:23) | Supervisor pid 46156 alive, cycle 37, heartbeat 32 s old. All 6 components `healthy`. Listeners: `127.0.0.1:3000` node 29104, `127.0.0.1:8001` python 10020, `127.0.0.1:20241` cloudflared 27468. Redis PING returned +PONG. Local: API /health 200, API /auth/me 401, web /login 200, web proxy /auth/me 401. Public `https://build-ebooks-heading-scoring.trycloudflare.com` /login **200**, /api/v1/auth/me **401**. |
| E2 | Win32_Process listing of the stack | Under supervisor 46156: web node 29104, API venv launcher 23248 (real interpreter 10020), worker wrapper node 27436 with exactly one `celery ... beat` root (9884) and one `celery ... worker` root (29068), each with its venv-launcher child, and cloudflared 27468. |
| E3 | `N0073_ver_kill.ps1 -Component web -KillPid 29104` | Killed 15:19:25.9. Supervisor logged `web: healthy -> dead` at 15:19:33 and relaunched pid 29628 at 15:19:35. Status.json showed `healthy` under the new pid at +46.4 s. **Recovered in 46 s.** |
| E4 | `N0073_ver_kill.ps1 -Component worker -KillPid 27436` | Killed 15:20:25.3. Supervisor logged `stop tree 27436 (worker wrapper exited; orphans of dead root): nothing running` at 15:20:41 and relaunched wrapper 12848 at 15:20:42. Status.json showed `healthy ... worker=1 beat=1` at +50.4 s. **Recovered in 50 s.** |
| E5 | Win32_Process listing after E3 and E4 | Exactly one beat root (35416, child 27276) and one worker root (46640, child 48560), both under wrapper 12848. The old celery pids 9884, 29068, 46528 and 28064 are gone. The web is now 29628. |
| E6 | `node scripts/dev-worker.js` (CIP_SUPERVISOR_CHILD not set) | Exit 1: "The CIP always-on supervisor (pid 46156) is running and already runs the worker. Refusing to start a second one." The guard is the first statement in `main()`, before any celery cleanup, so the test was safe to run. |
| E7 | A second copy of `scripts\cip-supervisor.ps1` started hidden | Exited after 1290 ms with code 0. Log: `15:22:44 [pid 37232] another supervisor is already running; exiting.` |
| E8 | `scripts/cip-supervisor-install.ps1 -Check` | Exit 0. Startup shortcut present in the per-user `...\AppData\Roaming\...\Startup\CIP always-on.lnk`. It runs `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "<repo>\scripts\cip-supervisor.ps1"` with window style 7. The desktop shortcuts `CIP status.url` and `CIP public link.url` are present, and the public one holds the current link. |
| E9 | `Get-ScheduledTask -TaskName '*CIP*'`; Get-Service filtered on cip, cloudflared, celery and redis | 0 scheduled tasks and 0 services. |
| E10 | `N0073_ver_gate_probe.ps1` (this run; it loads `Test-SessionMode`, `Get-AuthOpenEvidence` and `Get-TunnelGate` from the real script by AST and fakes the HTTP codes) | **36/36 PASS**, parse errors 0. See criterion 3. |
| E11 | Grep for regex or bracket use in `cip-supervisor*.ps1` and `pilot-tunnel.ps1` | No bracketed URL regex. The only regex is in pilot-tunnel.ps1:13, `Select-String -Pattern '^CIP_AUTH_MODE=session'` (an anchored literal for the .env check, not a URL). Hostname parsing: `ConvertFrom-Json` on `/quicktunnel` `.hostname` in cip-supervisor.ps1:680-683 and `Invoke-RestMethod` on `/quicktunnel` in pilot-tunnel.ps1:47-48. |
| E12 | Grep in `cip-supervisor*.ps1` and `supervisor-guard.cjs` for powercfg, registry, firewall/netsh, scheduled tasks/schtasks, services, docker, psql/SQL/sqlalchemy, SetThreadExecutionState, RunAs, Set-ExecutionPolicy and machine/user-scope SetEnvironmentVariable | No hits apart from process-scope `SetEnvironmentVariable(..., 'Process')` (cip-supervisor.ps1:428 and :434, saved and restored around Start-Process) and the `[InternetShortcut]` text of the .url files. |
| E13 | Supervisor log filtered on adopted, started, already running, error, not written, CLOSING and gated | 14:57:22 `supervisor started, pid 46156`. Then `wsl: adopted running process 4980` (14:57:22), `worker: adopted running process 31600` (14:57:23), `api: adopted running process 39224` (14:57:26). No `error`, `not written`, `CLOSING` or `gated` lines since 14:57. |
| E14 | `-LogFile web.log.1` and `-LogFile web.log.2` | Both generations exist and end in `Ready in 6.1s` and `Ready in 5.2s`. |
| E15 | `apps/web/package.json` | `"start": "next start -H 127.0.0.1 -p 3000"`. |
| E16 | Re-reading status after all tests (15:25:06) | All 6 components `healthy`, cycle 50. The link is unchanged, public 200/401. |

## Verdicts per criterion

### 1. One supervisor starts every missing component and restarts any that die, checking at least every 60 s: **VERIFIED_WITH_LIMITATIONS**
- Re-executed: web 46 s (E3) and worker wrapper 50 s (E4), both through new launches. After the worker kill there was exactly one worker and one beat (E5). Detection took 8 s and 16 s after the kill; the restart followed 1-2 s after detection.
- Cadence: the code uses `$CycleSeconds = 30`. Measured: 50 cycles in 27.7 min (14:57:22 to 15:25:06), about 33 s per cycle.
- Code review: each component has a start path. `Invoke-WslKeeper` (`wsl.exe -d Ubuntu ... sleep infinity`), `Invoke-Redis` (`service redis-server start`), `Invoke-Worker` (dev-worker.js with CIP_ENABLE_DEV_BEAT=1), `Invoke-Api` (uvicorn 127.0.0.1:8001, no --reload), `Invoke-Web` (next start -H 127.0.0.1) and `Invoke-Tunnel` (cloudflared, gated).
- Limitation: I did **not** kill the API, Redis, the WSL keeper or cloudflared. I left cloudflared alone so Warren's link would not change. For those I rely on code review plus the implementer's measurements (API 53 s, Redis 51 s, tunnel 56 s), which I did not re-execute. I also did not measure a cold start with no component running.
- Observation (reliability): the "≤ 60 s" check interval holds in steady state. It stretches in two cases:
  - **During a start.** `Invoke-Redis` can block for up to 60 s plus 10 s, and the tunnel start can block for up to 30 s, so a cold-start cycle can take well over 60 s.
  - **By design after repeated failures.** Backoff waits 30, 60, 120 and then 300 s between restarts. This is flap protection, not a defect.

### 2. Starts at logon without admin: **VERIFIED_WITH_LIMITATIONS**
- Per-user Startup shortcut present and pointing at the supervisor (E8). No scheduled task or service exists (E9). The install script writes only to the user's Startup, Desktop and LOCALAPPDATA folders.
- Limitation: I did not observe an actual logon or reboot. The evidence is that the shortcut exists and has the right target, not that the stack came up after a reboot.

### 3. Web binds 127.0.0.1 only; tunnel gate; closure on positive evidence; a 5xx is not auth-open: **VERIFIED**
- Bind: the only listener on 3000 is `127.0.0.1` (E1). The start command uses `-H 127.0.0.1` (E15 and the supervisor log). `Invoke-Web` replaces any non-127.0.0.1 listener on 3000 (cip-supervisor.ps1:590-598).
- Gate (`Get-TunnelGate`, :650-659): the tunnel refuses to start unless all four hold: `Test-SessionMode`, API /auth/me = 401, web /login = 200 and proxy /auth/me = 401. Re-executed in E10: each of 500/502/503/0 on the API or the proxy refuses, web /login 500 refuses, and `.env` set to dev refuses.
- `Test-SessionMode` was re-executed in E10:
  - `session`, and `"session" # comment`, are accepted.
  - These are rejected: `dev`, a later `dev` assignment that overrides an earlier `session`, a commented-out line, a missing .env, and a process `CIP_AUTH_MODE=dev` that overrides a .env `session`.
- **Plant-false (E10):** with session mode on, 500/502/503/0 on the API /auth/me, the proxy /auth/me or the public /auth/me each returned **no** auth-open evidence. A 200 on any of the three returned evidence. `.env` no longer saying session also counts as evidence (fail-closed).
- Latch (code review, :709-725): positive evidence sets `$tunnel.ClosedReason`, stops every quick tunnel and returns. Every later cycle re-stops any quick tunnel and reports `closed`. Nothing clears `ClosedReason` except a new supervisor process; `Invoke-StopFlag` with `-Component tunnel -Restart` does not reset it. So the tunnel is closed and not restarted.
- I could not read `apps/api/.env` directly (the hook blocks it as a sensitive path). Live session enforcement is shown by behaviour instead: API /auth/me 401, proxy 401, public 401, and the tunnel is `healthy`, not `gated` or `closed` (E1).
- Observation (security/reliability, safe direction): if `.env` is briefly unreadable or missing, for example during an editor save, `Test-SessionMode` returns false. That latches the tunnel closed until the supervisor is restarted. This fails closed and is not a defect, but the only recovery is `cip-supervisor-stop.ps1 -Restart`.

### 4. Public address from cloudflared /quicktunnel into status; no bracketed URL regex: **VERIFIED**
- `Update-Hostname` reads `http://127.0.0.1:<metrics>/quicktunnel` as JSON `.hostname` and checks it with `Test-HostnameShape`: it must end in `.trycloudflare.com` and contain only letters, digits, `-` and `.`. That stops a crafted value reaching the .url file or the HTML. Status.json `link.hostname` and `link.url` carry the result (E1). There is no bracketed URL regex in the supervisor scripts or in pilot-tunnel.ps1 (E11).

### 5. Public /login 200 and unauthenticated /api/v1/auth/me 401 now: **VERIFIED**
- E1 (15:18:23): `https://build-ebooks-heading-scoring.trycloudflare.com` /login 200, /api/v1/auth/me 401. E16 confirms the same at the end. The supervisor's own public checks logged 200/401 at 15:06, 15:11, 15:16 and 15:21.
- Limitation: these codes come after my web and worker kills, not after a tunnel kill. The post-tunnel-kill public check is the implementer's evidence (15:05:31).

### 6. No cip business-table writes by the supervisor, no Docker, no admin-only setting changed: **VERIFIED**
- The supervisor runs no SQL and has no database client. It does not use Docker, powercfg, the registry, the firewall, scheduled tasks, services or keep-awake (E12, E9). It changes only process-scope environment variables for its children.
- Note (per decision "beat on"): Celery beat, which the supervisor starts, does run scheduled tasks that may write. Observed in worker.err.log at 15:24: `imports.reap_stale_running_jobs` (marked_failed 0) and `reports.run_due_schedules` (due_count 0). Those writes come from the product's beat, as accepted, not from the supervisor itself.

### Additional checks
- Mutex single instance: **VERIFIED** (E7).
- dev-worker.js refuses while the supervisor is live: **VERIFIED** (E6). `supervisor-guard.cjs` requires the pid to be alive and the heartbeat to be under 10 min old, and exempts `CIP_SUPERVISOR_CHILD=1`.
- Adoption of healthy processes: **VERIFIED** by log (E13) and code (`Set-Adopted` in each `Invoke-*`). `Invoke-StopFlag` stops only non-adopted worker, API and web processes.
  - Historical: the log shows the pre-fix supervisor writing `api: adopted running process 19756` (a dead PID) about every 33 s from 14:38 to 14:57. That matches implementer finding 1 and has stopped since 14:57:26.
- Log rotation: **VERIFIED**. `Write-Log` rolls supervisor.log to `.1` at 10 MB, which is one generation. `New-LogPair` keeps 3 generations per component on each launch, and both web.log.1 and web.log.2 exist (E14). The supervisor-log roll at 10 MB was not exercised.

## Findings (not N-0073 defects)
- OBSERVATION: worker.err.log 15:24:16 shows `running_import_job_reaper: celery inspect returned no workers`. A plausible cause is that `--pool solo` cannot answer inspect while it is running the reaper task itself. The reaper handled it safely (`inspected: False, marked_failed: 0`). This is a product-side question for the import reaper, not a supervisor fault.
- OBSERVATION: the orphan-kill branch for celery children of a dead wrapper did not trigger in E4, because the children had already exited ("nothing running"). The end state was still exactly 1 worker and 1 beat, but the branch itself was not exercised by this run.

## Limitations (collected)
1. Only web and the worker wrapper were killed in this run. API, Redis, the WSL keeper and cloudflared recovery rely on code review plus the implementer's evidence. cloudflared was deliberately not killed, to keep Warren's link.
2. No cold start from nothing and no real logon or reboot were observed.
3. The cycle can exceed 60 s while Redis or the tunnel is starting, and by design during backoff.
4. `apps/api/.env` was not read (the hook blocks it). Session mode is inferred from live 401s and the ungated tunnel state.
5. The independence is R2 with the same model family, not a different model.

## End state
The supervisor is RUNNING (pid 46156) and all 6 components are healthy at 15:25:06. Web is now pid 29628 and the worker wrapper 12848, both relaunched by the supervisor after my kills. The public link is unchanged: `https://build-ebooks-heading-scoring.trycloudflare.com/login`. Everything I killed came back.

At 15:31:56 a re-check gave the same result: all 6 components healthy, public /login 200, /api/v1/auth/me 401.

## Ledger (run RUN-20261007-N0073-VER, actor gov-008)

The node had no lease, so no LEASE_HELD case came up.

| Event | Node revision | Ledger revision |
|---|---|---|
| `node.verification` kind behavioral, state pass (`N0073_ver_behavioral.json`) | 13 -> 14 | 1603 |
| `node.verification` kind referent, state pass, path `scripts/cip-supervisor.ps1` (`N0073_ver_referent.json`) | 14 -> 15 | 1604 |
| `node.stage` -> verify, with the verdict as stage_note (`N0073_ver_stage_verify.json`) | 15 -> 16 | 1605 |

`program.py verify`:
- integrity_ok is true.
- gates_ok is false, but only because of existing acknowledged gate debt on N-0006, N-0013, N-0014, N-0015 and N-0016. No issue names N-0073.
- The status is still `in_progress`. Acceptance is Warren's.

Audit helpers written by this run (not product): `N0073_ver_kill.ps1`, `N0073_ver_gate_probe.ps1`.
