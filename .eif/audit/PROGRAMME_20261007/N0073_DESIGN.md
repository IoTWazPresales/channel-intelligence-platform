# N-0073 feature definition: always-on stack (2026-10-07)

Lenses: architecture-specialist (lead), product-manager, reliability-sre-specialist. Read only. Nothing was run. Builds on N0073_DISCOVERY.md.

## CHALLENGE (risks, with evidence)

1. **Redis without a sudo password.** `restart-dev.ps1:38` uses `sudo` inside a visible window. Use `wsl -d Ubuntu -u root -- service redis-server start`. This needs no password and no admin rights.
2. **WSL shuts itself down when idle.** A distro whose last `wsl.exe` client exits can stop after a few seconds, and Redis stops with it (discovery: Ubuntu "Stopped"). Fix: the supervisor keeps one hidden child running, `wsl -d Ubuntu -u root -- sleep infinity`, and restarts it if it dies. Do not edit `.wslconfig` or `/etc/wsl.conf`.
3. **The supervisor can die without anyone noticing.** A Startup entry runs once per logon and never relaunches it. Fixes: wrap every check cycle in try/catch so an error cannot end the loop; write a heartbeat into the status file on every cycle; the link page shows "supervisor stale" when the heartbeat is more than 3 minutes old.
4. **Two Celery consumers.** `dev-worker.js:124-150` kills every `app.worker.celery_app` process before it starts. If someone runs `pnpm dev:worker` or `restart-dev.ps1` by hand while the supervisor is running, they kill each other in a loop. Fix: both scripts refuse to start while the supervisor's PID file points at a live process.
5. **`next start` needs a finished build** (`.next/BUILD_ID`). The supervisor never builds on its own. With no build it reports `web: needs build` and stops retrying.
6. **Web listens on all interfaces today.** `package.json:8` has `start = next start -H 0.0.0.0` (pid 34400). The supervisor treats a 3000 listener on `0.0.0.0` or `::` as unhealthy: it stops that process tree and starts a loopback one. Change `start` to `-H 127.0.0.1`.
7. **Taking over healthy processes.** The API (`dev:api`, with `--reload`) and cloudflared pid 9960 are already healthy. Restarting cloudflared would change the address, so the supervisor adopts any process that passes its checks.
8. **Logs grow without limit.** Uvicorn, Next and Celery at info level, with beat ticking every 120 s, add up over weeks.
9. **Sleep.** When the PC sleeps, everything stops. After a long sleep or outage, the quick-tunnel hostname can stop resolving ("Tunnel not found"/530) even though the process is alive. Only a public check catches this.
10. **Exposure while nobody is watching.** Auth can be loosened (a `.env` edit) while the tunnel stays up. The supervisor must close the tunnel when it sees positive evidence that auth is open.
11. **Execution policy.** Group Policy may block `-ExecutionPolicy Bypass`. Check with `Get-ExecutionPolicy -List` before installing.
12. **Beat writes a schedule file.** It writes `celerybeat-schedule*` into `apps/api`, and `.gitignore` does not cover it. Add it to `.gitignore`.

## DESIGN

**Files**
- `scripts/cip-supervisor.ps1`: the check loop.
- `scripts/cip-supervisor-install.ps1 [-Uninstall]`: creates or removes the per-user Startup shortcut. The shortcut lives in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` and runs `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File <repo>\scripts\cip-supervisor.ps1`. It also creates the desktop shortcuts. No admin needed.
- `scripts/cip-supervisor-stop.ps1 [-Component x] [-Restart]`: writes `stop.flag`. The supervisor then stops what it owns and exits.
- Small edits:
  - `dev-worker.js` and `restart-dev.ps1`: add the guard from Challenge 4.
  - `pilot-tunnel.ps1:46`: replace the regex with a read of `/quicktunnel`.
  - `package.json`: change `start` to `-H 127.0.0.1`.
  - `.gitignore`: add `celerybeat-schedule*`.

**State** lives outside the repo, under `%LOCALAPPDATA%\CIP\always-on\`:
- `supervisor.pid`
- `status.json`
- `link.html`
- `logs\<component>.log` and `.err.log`

**Running only once.** A named mutex, `Local\CIP-AlwaysOn`, is taken with `WaitOne(0)`. A second copy exits at once. Windows releases the mutex when the process dies, so a stale lock cannot block a restart.

**Loop.** Every 30 s, checking components in dependency order. Before restarting a component, the supervisor waits 0, 30, 60, 120, then at most 300 s. More than 5 restarts in 30 minutes marks the component `flapping`; it keeps retrying at the 300 s cap. Each launch gets new log files; the old ones become `.1` and `.2` (3 generations kept). The supervisor's own log rolls over at 10 MB.

**Components**

| Component | Healthy when | Start command | Restart when |
|---|---|---|---|
| WSL keeper | its child process is alive | `wsl -d Ubuntu -u root -- sleep infinity` | it dies |
| Redis | TCP 6379 answers `PING` with `+PONG` | `wsl -d Ubuntu -u root -- service redis-server start` | 2 checks fail in a row |
| Worker + beat | exactly 1 `celery ... worker` and 1 `celery ... beat` process, and Redis is up | `node scripts/dev-worker.js`, with `CIP_ENABLE_DEV_BEAT=1` and `PYTHONUNBUFFERED=1` | the wrapper exits (it exits when either child dies), or the worker/beat count is wrong |
| API | `GET 127.0.0.1:8001/health` returns 200 | `apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`, from `apps/api`, without `--reload` (a `git checkout` must not restart it mid-request) | 3 checks fail in a row |
| Web | `/login` returns 200, `/api/v1/auth/me` returns 401, and the only listener on 3000 is `127.0.0.1` | `node node_modules/next/dist/bin/next start -H 127.0.0.1 -p 3000`, from `apps/web` (no pnpm wrapper, so the PID is the real process) | 3 checks fail in a row |
| Tunnel | the process is alive and `127.0.0.1:20241/ready` returns 200 | see below | see below |

`CIP_ENABLE_DEV_BEAT=1` must reach both the worker and beat, because each task checks `dev_beat_disabled()` again when it runs (`tasks.py:804,838`). A healthy API already running from `dev:api` is adopted.

**Tunnel**
- Start command: `cloudflared tunnel --url http://127.0.0.1:3000 --protocol http2 --metrics 127.0.0.1:20241 --no-autoupdate`.
- Gate before every start: `apps/api/.env` contains `CIP_AUTH_MODE=session`, the API `/auth/me` returns 401, web `/login` returns 200, and the web proxy `/auth/me` returns 401.
- Restart only when one of these is true:
  - the process is dead;
  - `/ready` has not returned 200 for 10 minutes;
  - the public `/login` has not returned 200 for 10 minutes (checked every 5 minutes).
- Kill the tunnel without restarting it when there is positive evidence that auth is open: an unauthenticated `/auth/me` returns 200, or `.env` loses session mode. A 5xx from a downstream component leaves the tunnel running.
- Adoption: if a cloudflared process is already running and `/quicktunnel` answers, it is adopted.

**Current link**
1. The supervisor reads it with `Invoke-RestMethod http://127.0.0.1:20241/quicktunnel` and uses the `.hostname` field. No regex is involved.
2. It writes the link into `status.json` along with the component states, PIDs, adopted flags, restart counts and heartbeat.
3. It regenerates `link.html`: the link as large text, a Copy button, the component table, and a warning when the heartbeat is stale.
4. When the hostname changes, it rewrites the desktop shortcut `CIP public link.url`. A second desktop shortcut, `CIP status.url`, opens `link.html`.

**Stop and restart.** `cip-supervisor-stop.ps1` stops the supervisor, then the process trees it owns, then cloudflared. It leaves Redis and WSL running.

**Env.** The supervisor never sets `CIP_LISTING_LIVE_FETCH` or `CIP_LISTING_CAPTURE_SCHEDULE`. On each start it records whether either is present in the inherited environment.

## WHAT WAKES UP (once worker and beat are running)

| Job | Schedule | What it does | Writes to cip? |
|---|---|---|---|
| `imports.reap_stale_running_jobs` | every 120 s | marks stuck `running` import jobs as failed | yes |
| `imports.cst_advance_report_slots` | 06:15 daily (Celery default timezone, UTC, if nothing overrides it) | creates and advances CST expected-report slots | yes |
| `listing_capture.poll_listings` | every 30 min | does nothing unless `CIP_LISTING_CAPTURE_SCHEDULE` is set, listings exist, and `CIP_LISTING_LIVE_FETCH` is set (default off) | only when all three are true |
| `reports.run_due_schedules` | on an interval | delivers enabled schedules and sends email | yes |
| `cpor.fetch_daily_fx_rate` | 06:30 daily | fetches the rate from Frankfurter and stores it | yes |

The report and FX jobs already run inside the API process (`main.py:29-31`). Beat adds a second runner for each:
- The report runner locks rows with `skip_locked` (`report_schedule_runner.py:92`). This makes double delivery unlikely, but it has not been measured.
- The FX job uses `ensure_today_rate`, which is idempotent by its name; the code was not checked.

Any tasks still waiting in Redis run as soon as the worker starts.

## OUT OF SCOPE

- Named tunnel and domain (N-0074).
- Postgres.
- Sleep and Windows Update settings.
- Docker, Windows services, NSSM, or anything needing admin.
- Auth changes.
- Alerts sent off the machine.

## OPEN QUESTIONS FOR WARREN

1. **Turning on beat makes the app write scheduled rows to cip** (reaper, CST slots, FX, report emails). Acceptance criterion 6 ("no writes") can then only cover the supervisor itself, not the app. Do you confirm beat on, including CST slots advancing every day?
2. **The always-on API runs without `--reload`.** After code changes, someone restarts it with `cip-supervisor-stop -Component api -Restart`. Is that acceptable?
3. **Keep-awake (opt-in `-KeepAwake`).** Should the supervisor stop the PC from idle-sleeping while it runs? It would do this through `SetThreadExecutionState`, a per-process call that changes no setting.
4. **Leftover tasks.** Before the first worker start, should tasks already waiting in Redis be listed for you to decide on, or run as they are?
