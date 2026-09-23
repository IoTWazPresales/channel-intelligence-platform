# N-0036 implementation evidence: BACKLOG-206 (API loopback bind)

Run: N0036_IMPL_20260924 · 2026-09-23T22:35Z (UTC) · branch feat/ns-2-brief-nav-collapse

## Outcome: BLOCKED. Product-source write denied (authority boundary)

Every write to product source was denied by the EIF guard with `OUT_OF_CHANGE_SCOPE`:

- `Edit scripts/dev-api.js` -> `OUT_OF_CHANGE_SCOPE: path outside accepted change scope: scripts/dev-api.js`
- `Write scripts/api-bind-host.cjs` -> same
- `Write scripts/api-bind-host.test.cjs` -> same

This is a scope/authority boundary, so the work package stopped. No shell-based edit was attempted to get around it.
Nothing was committed, the API was **not** restarted (a restart without the code change proves nothing and would take down the operator's running API window), and docs/BACKLOG.md was not stamped.
Also: the `Skill` tool is denied by the Claude Code adapter (`SHIM_TOOL_UNMAPPED`), so the three lenses (platform-devops, test-engineering, reliability-sre) were applied inline.

**Grant required:** accepted change scope for N-0036 must include at least
`scripts/dev-api.js`, `scripts/api-bind-host.cjs`, `scripts/api-bind-host.test.cjs`, `docs/BACKLOG.md`,
`docs/PILOT_TUNNEL_RUNBOOK.md`, and optionally the doc callers listed below (`README.md` untouched; `AGENTS.md`,
`docs/LOCAL_DEV_WINDOWS.md`, `docs/BACKUP_AND_DR.md`, `infra/docker/README.md`).

## Before state (measured)

```
netstat -ano | grep ':8001'
  TCP    0.0.0.0:8001           0.0.0.0:0              LISTENING       24104
  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING       19900   (web, out of scope)
.cip-dev-pids/api.pid = 20524 (dev-api.js parent)
```

HTTP (before):

| Probe | Result |
|---|---|
| `curl http://127.0.0.1:8001/health` | 200 |
| `curl http://127.0.0.1:8001/health/ready` | 200 |
| `curl http://127.0.0.1:8001/api/v1/health` | **404**: no such route |
| `curl http://127.0.0.1:3000/api/v1/health` | **404**: proxied, same 404 from API |
| `curl http://127.0.0.1:3000/api/v1/auth/me` | 401 (proxy reaches API; gate enforces) |
| `curl http://127.0.0.1:8001/api/v1/auth/me` | 401 |
| `curl http://localhost:8001/api/v1/health` | 404 via remote_ip 127.0.0.1 |
| `curl http://[::1]:8001/api/v1/health` | 000 (no IPv6 listener: 0.0.0.0 is IPv4-only already) |

**Finding (criterion 3 wording):** `/api/v1/health` does not exist. Health lives at `/health` and `/health/ready`, which are **not** under the
`/api/v1` proxy prefix, so the web proxy can't reach them. A correct proxy-reachability probe is `GET http://127.0.0.1:3000/api/v1/auth/me` -> 401
(the proxy reaches the API and the gate answers), plus `GET http://127.0.0.1:8001/health` -> 200 directly.

## localhost resolution on this host (measured)

| Resolver | Order |
|---|---|
| Node v24.13.0 `dns.lookup('localhost',{all:true})` | `127.0.0.1` (v4), `::1` (v6); default lookup -> `127.0.0.1` |
| Python (apps/api venv) `socket.getaddrinfo('localhost',8001)` | `127.0.0.1`, `::1` |
| .NET `[System.Net.Dns]::GetHostAddresses('localhost')` (PowerShell) | `127.0.0.1`, `::1` |
| curl `localhost:8001` | connected via `127.0.0.1` |

Conclusion: every resolver on this host tries IPv4 loopback first. The API has **never** had an IPv6 listener (`0.0.0.0` is IPv4-only;
`[::1]:8001` refused today). A `127.0.0.1` bind therefore does not change what `localhost` callers reach: the regression trap does not apply on this host.
Repointing docs to `127.0.0.1` is still worth doing for hosts where `::1` sorts first.

## In-repo callers of the API host (search, excluding `.wt-*` worktrees, node_modules, .venv, .next, .eif)

Code already on 127.0.0.1 (no change needed):
- `apps/web/src/app/api/v1/[[...path]]/route.ts:29,35`: fallback `http://127.0.0.1:8001` (dev and prod); no `apps/web/.env*` sets `NEXT_PUBLIC_API_URL`/`CIP_API_INTERNAL_URL` (only `.env.local.example`, commented `localhost:8010` Docker example).
- `scripts/dev-web.js:30`, `scripts/dev-api-web-stable.cjs:14`, `scripts/dev-all-with-notice.cjs:12`: `CIP_API_INTERNAL_URL` default `http://127.0.0.1:8001`.
- `apps/api/scripts/ops/*.py` (verify_browser_query, session_e_*, session_d_*, browser_db_parity_audit): all `http://127.0.0.1:8001`; `session_d_run_api.py:105` already binds `127.0.0.1`.
- `apps/web/e2e/wipe-and-products-delete.spec.ts`, `scripts/docker-e2e.cjs`: `127.0.0.1:8001`. `apps/web/playwright.config.ts`: web on 127.0.0.1, no API host.
- Celery worker (`scripts/dev-worker.js`, `apps/api/app/**`): no HTTP calls to the API found (grep `localhost:8001|API_URL` in `apps/api/app`: no matches). Worker talks to Redis/DB only.
- `apps/api/Dockerfile:24` `--host 0.0.0.0 --port 8000`: container bind, required for Docker port mapping; not the dev path; out of scope.

Docs/runbooks that name `localhost:8001` or the `0.0.0.0` bind (to repoint once scope is granted):
- `docs/PILOT_TUNNEL_RUNBOOK.md:14`: API bind row says `0.0.0.0:8001` -> `127.0.0.1:8001`.
- `docs/PILOT_TUNNEL_RUNBOOK.md:51,63,92,94,96`: `http://localhost:8001` -> `http://127.0.0.1:8001`; line 63 "LAN-visible on 0.0.0.0" -> loopback only.
- `AGENTS.md:151`, `docs/LOCAL_DEV_WINDOWS.md:160`, `docs/BACKUP_AND_DR.md:60-61`, `infra/docker/README.md:75`, `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc:41`: `localhost:8001` (all work on this host per resolution above; cosmetic).
- `docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md:48`: historical handover, `--host 0.0.0.0`; leave as history.

## Prepared change (not applied: denied)

1. `scripts/api-bind-host.cjs` (new): `DEFAULT_API_HOST='127.0.0.1'`, `resolveApiBindHost(env)` (trimmed `CIP_API_HOST` else default), `isLoopbackHost(host)`.
2. `scripts/dev-api.js`: require it; `--host resolveApiBindHost(process.env)` replacing `process.env.CIP_API_HOST || '0.0.0.0'`; warn when override is non-loopback.
3. `scripts/api-bind-host.test.cjs` (new, `node --test`): default is 127.0.0.1; empty/whitespace falls back; override `0.0.0.0` and `::1` kept; loopback classification; source guard that dev-api.js no longer has the `|| '0.0.0.0'` default.
4. Docs repoint as listed; BACKLOG-206 Status -> Done with commit.
5. Verify: restart API (kill PID on :8001 + dev-api.js parent from `.cip-dev-pids/api.pid`, `pnpm dev:api` in background), `netstat` shows `127.0.0.1:8001` only, `curl 127.0.0.1:8001/health` 200, `curl 127.0.0.1:3000/api/v1/auth/me` 401 (proxy reachability).

## Tests run
None: no code change was permitted.
