# N-0073 discovery — always-on stack on this PC (2026-10-07, run RUN-20261007-N0073-GOV)

Observed on the running machine (FACT unless marked):

| Component | Observed now | Survives reboot today? |
|---|---|---|
| Postgres 18 | Windows service `postgresql-x64-18`, Running, StartType Automatic, :5432 (bound `0.0.0.0` and `::`) | Yes |
| Redis | **Not listening on 6379.** Comes from WSL `Ubuntu` (`wsl -l -v`: Stopped). `scripts/restart-dev.ps1` starts it with `sudo service redis-server start` in a kept-open window | No |
| Celery worker | Not running (no broker). `scripts/dev-worker.js` skips beat on Windows unless `CIP_ENABLE_DEV_BEAT=1` (BACKLOG-038). Beat schedule carries `listing-capture-poll` every 30 min, FX and report jobs | No |
| API | python pid 19756 on `127.0.0.1:8001` (`pnpm dev:api`, N-0036 loopback) | No |
| Web | node pid 34400 on **`0.0.0.0:3000`** (production build `wNwZD3ubHBfWiNWT4CdGX`). `apps/web/package.json` `start` = `next start -H 0.0.0.0`; the pilot script overrides to `127.0.0.1` | No |
| Tunnel | `cloudflared.exe tunnel --url http://localhost:3000 --protocol http2`, pid 9960, started 11:59; metrics `127.0.0.1:20241`; `/quicktunnel` returns `{"hostname": "mothers-briefing-honey-infants.trycloudflare.com"}`; public `/login` 200, `/api/v1/auth/me` 401 | No; address changes each start |

Existing capabilities to preserve:
- `scripts/pilot-tunnel.ps1`: refuses unless `CIP_AUTH_MODE=session`; refuses unless API and web proxy answer 401 on `/api/v1/auth/me`; web on `127.0.0.1`.
- `scripts/restart-dev.ps1` / `scripts/stop-dev.ps1`: dev stack with PID files in `.cip-dev-pids/`.
- `scripts/dev-worker.js`: Redis preflight; kills orphan Celery before spawning (one consumer only).

Constraints and findings:
- A logon scheduled task was refused earlier today with access denied (Cursor thread, not re-measured). Per-user Startup folder needs no admin.
- `pilot-tunnel.ps1` line 46 reads the address with a bracketed regex. The EIF guard crashes on a shell command containing a bracketed URL pattern (`ValueError: Invalid IPv6 URL`), which wedged every session today. The metrics endpoint `/quicktunnel` removes the need for the regex.
- Managed Chrome blocks `*.trycloudflare.com` by organisation policy (PILOT_TUNNEL_RUNBOOK §H). Company users need N-0074 (named tunnel on Warren's domain).
- Sleep/hibernate and Windows Update reboots are machine settings Warren controls; the agent changes none.
- Runbook §L: quick tunnel "not yet safe for leaving the tunnel running unattended overnight". Since then N-0037 (login rate limit and lockout) and N-0055 (tenant scoping) are complete. Always-on is Warren's explicit request (2026-10-07).
