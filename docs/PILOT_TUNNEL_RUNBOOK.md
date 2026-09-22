# Pilot tunnel runbook — CIP over Cloudflare Quick Tunnel (R0/month)

**Date:** 2026-09-21 · **EIF node:** N-0033 · **Scope:** infrastructure only. No CIP redesign, no business-logic change, no schema change. Quick Tunnel: free, no account, no domain, no DNS, HTTPS from Cloudflare's edge.

> Code is evidence. Everything under "Verified" below was measured on 2026-09-21; anything else is a claim to re-verify.

---

## A. Current architecture

| Layer | What | Where it binds |
|---|---|---|
| Web | Next.js 15 App Router, **production build** (`next build` + `next start`) | `127.0.0.1:3000` — overridden from the package `start` script's `0.0.0.0` |
| API | FastAPI + uvicorn via `pnpm dev:api` | `0.0.0.0:8001` (dev script; **not** fronted by the tunnel) |
| Browser → API | same-origin `/api/v1/*` proxied server-side by `apps/web/src/app/api/v1/[[...path]]/route.ts` to `127.0.0.1:8001` | no cross-origin, no CORS, `NEXT_PUBLIC_API_URL` **unset** |
| DB / Redis / worker | Postgres `localhost:5432` (`cip`), Redis `:6379`, Celery | never exposed |
| Auth | `CIP_AUTH_MODE=session` in `apps/api/.env`; bearer tokens from `POST /api/v1/auth/login`; PBKDF2-SHA256 × 260k; client `redirectToLoginOn401` | router-level gate on every `/api/v1` route (`26a6e1a`) |
| Tunnel | `cloudflared 2026.9.1` quick tunnel, `--protocol http2` (QUIC was flaky on this network) | fronts `http://localhost:3000` only |

No WebSockets in app code; no SSE anywhere (Quick Tunnel's SSE limitation does not apply). `/docs`, `/openapi.json`, `/redoc` exist on `:8001` and are **unreachable** through the tunnel (verified 404).

## B. Security findings

1. **Before:** effective auth mode was `stub` (0-byte `.env`) → every anonymous request was `admin@local`, identity headers forgeable. **Fixed** by `CIP_AUTH_MODE=session` (Warren set passwords first).
2. **Before:** with session mode on, auth was per-endpoint — **127 of 207 sampled GET routes returned 200 with no token** (customers, products, imports, CPOR settlement, steward queue, `GET /dev/database-wipe`…). **Fixed** by a router-level `get_current_user` dependency with only `/auth/login` public → **0 / 207 open** after restart.
3. `POST /dev/database-wipe` still exists; requires `ALLOW_DB_WIPE=true` (default False) **and** now a bearer. Consider removing the router from non-dev builds later.
4. No login rate-limit or lockout (BACKLOG / Stage 3.4).
5. Tenant scoping incomplete: 34 of 58 endpoint modules never reference `tenant_id`. Acceptable for a single-tenant staff pilot; not for two tenants.
6. `cip` holds **real production data**. Every pilot user is trusted staff.

## C. Multi-user risks

- Two stewards acting on the same queue item → last write wins; no optimistic locking.
- Shared master data mutations are audited per actor (`decided_by`, `apply_actor`) but not conflict-protected.
- Uploads land in one `./storage/uploads` tree, namespaced by job, not by user.
- Long imports run on one Celery worker; a second user's job queues behind the first.
- A user who is signed out mid-session sees `/login`; their in-flight edits are lost (no drafts).

## D. Changes made (2026-09-21)

`apps/api/.env`: `CIP_AUTH_MODE=session` (not committed — `.env` is never committed). Router-level gate + `public_router` (`26a6e1a`). Test infrastructure for the gate and two stale fixtures (follow-up commit). `next build` + `next start -H 127.0.0.1`. cloudflared installed to `%LOCALAPPDATA%\cloudflared\cloudflared.exe` from the official GitHub release.

## E. Files changed

`apps/api/app/api/v1/router.py`, `apps/api/app/api/v1/endpoints/auth.py`, `apps/api/app/main.py`, `apps/api/tests/test_session_gate.py`, `apps/api/tests/conftest.py`, `apps/api/tests/test_commercial_planner_api.py`, `apps/api/.env` (local only), this runbook.

## F. Commands executed (the ones that matter)

```powershell
# passwords (Warren, stub mode, before the flip)
Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/v1/auth/users/1/set-password -ContentType 'application/json' -Body (@{new_password='<…>'} | ConvertTo-Json)
# mode flip + restart
Add-Content apps\api\.env "CIP_AUTH_MODE=session"; pnpm dev:api
# production web on loopback
pnpm --filter @cip/web build
pnpm --filter @cip/web exec next start -H 127.0.0.1 -p 3000
# tunnel
& "$env:LOCALAPPDATA\cloudflared\cloudflared.exe" tunnel --url http://localhost:3000 --protocol http2
```

## G. Local CIP URL

`http://127.0.0.1:3000` (login at `/login`). API `http://localhost:8001` (LAN-visible on `0.0.0.0` via the dev script; behind the gate).

## H. Public URL

Printed by cloudflared on each start as `https://<random-words>.trycloudflare.com`, and written to its log at **`%LOCALAPPDATA%\Temp\cloudflared-cip.log`** (`/c/Users/warren_eliason/AppData/Local/Temp/cloudflared-cip.log` from git-bash) if started per §I/§M below. **It changes on every restart** — do not write it into any config, doc or bookmark; always read the current one from the log. It also dies if the underlying `cloudflared` process is killed, crashes, or its registration expires after a long outage (reconnect then fails with `Unauthorized: Tunnel not found` — restart fresh, don't wait for it to heal itself). On 2026-09-21 it was verified once as: `/login` 200 · `/api/v1/auth/me` 401 · `/api/v1/customers` 401 · `/docs` 404 · `Server: cloudflare`, `CF-Ray …-JNB`; re-verified 2026-09-22 on a second network after the first blocked the tunnel outright (see §M).

**Warren's managed Chrome blocks `*.trycloudflare.com` by organisation policy.** Test from a phone on mobile data or an unmanaged browser. This is independent of the network-level block in §M — either one alone stops the tunnel path for a given browser/network combination, and both have been seen in this pilot.

## I. How to start it again

Copy the block below to `scripts\pilot-tunnel.ps1` (root `scripts/` is outside the agent's `change_paths`, so the file lives here in the runbook). It validates, starts what's missing, refuses to tunnel unless auth is in session mode, and prints the URL.

```powershell
# scripts\pilot-tunnel.ps1 — start CIP for a pilot and open a Cloudflare quick tunnel. R0/month.
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$cf = "$env:LOCALAPPDATA\cloudflared\cloudflared.exe"

function Up($url) { try { (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5).StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } } }

# 0. Safety gate: never tunnel a stub-auth API.
if (-not (Select-String -Path apps\api\.env -Pattern '^CIP_AUTH_MODE=session' -Quiet)) {
  throw "apps/api/.env must contain CIP_AUTH_MODE=session before exposing CIP. Refusing."
}
if (-not (Test-Path $cf)) { throw "cloudflared not found at $cf (install from https://github.com/cloudflare/cloudflared/releases)" }

# 1. API
if ((Up 'http://localhost:8001/health') -ne 200) {
  Start-Process pnpm -ArgumentList 'dev:api' -WindowStyle Minimized
  1..30 | ForEach-Object { if ((Up 'http://localhost:8001/health') -eq 200) { break }; Start-Sleep 2 }
}
if ((Up 'http://localhost:8001/api/v1/auth/me') -ne 401) { throw "API is not enforcing session auth (expected 401 on /auth/me without a token). Refusing." }

# 2. Web (production build on loopback). Stop any `next dev` on :3000 first — dev and build share .next.
$listening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
  if (-not $SkipBuild) { pnpm --filter @cip/web build; if ($LASTEXITCODE -ne 0) { throw 'next build failed' } }
  Start-Process pnpm -ArgumentList '--filter','@cip/web','exec','next','start','-H','127.0.0.1','-p','3000' -WindowStyle Minimized
  1..30 | ForEach-Object { if ((Up 'http://127.0.0.1:3000/login') -eq 200) { break }; Start-Sleep 2 }
}
if ((Up 'http://127.0.0.1:3000/login') -ne 200) { throw 'web /login is not 200' }
if ((Up 'http://127.0.0.1:3000/api/v1/auth/me') -ne 401) { throw 'proxy is not enforcing auth' }

# 3. Tunnel — URL is different every time; read it from the log.
$log = Join-Path $env:TEMP 'cloudflared-cip.log'
Start-Process $cf -ArgumentList 'tunnel','--url','http://localhost:3000','--protocol','http2' -RedirectStandardError $log -WindowStyle Minimized
$url = $null
1..40 | ForEach-Object { if (Test-Path $log) { $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1; if ($m) { $url = $m.Matches[0].Value } }; if ($url) { break }; Start-Sleep 2 }
if (-not $url) { throw "no trycloudflare URL in $log" }
"`nCIP pilot is up.`n  local : http://127.0.0.1:3000/login`n  public: $url/login   (changes on every restart)`n  stop  : Get-Process cloudflared | Stop-Process; then Ctrl+C the web and API windows`n"
```

## J. How to stop it

```powershell
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force   # tunnel first — the URL dies immediately
# then Ctrl+C the `next start` window, then the API window
```

Nothing persists: no service, no DNS record, no account.

## K. Phase 7 — two-user test plan (User A admin, User B viewer, different networks)

| # | Step | Expect |
|---|---|---|
| 1 | A opens the public URL | lands on `/login`, not on data |
| 2 | A signs in as `admin@local` | Overview renders; footer shows the account, not "Signed out" |
| 3 | B opens the same URL on a phone (mobile data) | `/login` |
| 4 | B signs in as `viewer@local` | read-only surfaces render; admin-only controls absent (`/admin/users/list` → 403 or hidden) |
| 5 | Both navigate simultaneously (A: Case book; B: Stock › Cover) | no cross-talk; each sees their own role's UI |
| 6 | A opens a case desk; B opens the same case | both read it; B has no settle/supersede CTAs |
| 7 | A edits a customer term; B refreshes | B sees A's change (shared data, by design) |
| 8 | A and B edit the **same** field, A saves first, B saves | B's save wins silently — record this as the known conflict behaviour (Risk C1) |
| 9 | A uploads a small import file (Import Center) | job appears for both; B cannot apply it |
| 10 | A runs a dashboard; B runs the same | identical numbers |
| 11 | **A signs out** | A → `/login`; **B's session continues** (tokens are per-session rows) |
| 12 | B signs out, then re-opens the URL | `/login`; no data visible without signing in |
| 13 | A checks `auth_session` rows after the test (read-only SQL) | one row per login, `revoked_at` set for both logouts |
| 14 | Steward actions by A appear with `decided_by` / `apply_actor` stamped | audit trail present |

Also check the browser console for errors on each surface and that static assets load over the tunnel (no mixed-content warnings).

## L. Safe enough for a small temporary pilot?

**Yes, with the conditions above:** trusted staff only, one tenant, tunnel stopped when not testing, URL never written down, passwords rotated after the pilot (both are placeholder-strength and were shared in chat). Not yet safe for: untrusted users, a second tenant, or leaving the tunnel running unattended overnight.

## M. LAN-direct alternative (same network, no tunnel)

For a colleague on the **same physical/Wi-Fi network** as the host machine, skip cloudflared entirely — no port-7844 dependency, no `*.trycloudflare.com` browser policy to run into.

1. Web already binds every interface by default: `apps/web/package.json`'s `start` script is `next start -H 0.0.0.0 -p 3000` (unmodified — a 2026-09-21 tunnel session had overridden this to `-H 127.0.0.1` at the command line for that run only, not by editing the file). Running `pnpm --filter @cip/web start` is sufficient; no code change needed.
2. Get the host's current LAN IP: `ipconfig` → the `IPv4 Address` under whichever adapter shows `Media State` connected (usually Wi-Fi or Ethernet). **This address is assigned per network and is not stable** — confirmed different across two networks in this pilot (`192.168.101.253`, then `192.168.50.253`), and it can change on a reboot or DHCP lease renewal even on the same network. Always re-check it rather than reusing a value from a prior session. If it needs to stay fixed, ask IT for a DHCP reservation on this machine's MAC address.
3. Open the port — **Warren runs this himself**, it is a system-settings change no agent performs:
   ```powershell
   New-NetFirewallRule -DisplayName "CIP web 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
   ```
   As of 2026-09-22 no port-scoped rule for 3000 or 8001 exists (checked read-only). There are pre-existing **program-scoped** inbound Allow rules on the **Public** profile for `node.exe` (system Node.js and Cursor's bundled copy) and `python.exe` (3.14 and 3.12) — these allow those binaries inbound on *any* port on a Public network, which is broader than the single-port rule above and predates this pilot; worth a security pass on its own, out of scope here.
   Once the rule exists, **the web server is reachable from any device on that network for as long as the process runs** — not just the one colleague it's intended for. Stop the `next start` process (or the firewall rule) when the pilot window is over, the same as stopping cloudflared.
4. Colleague browses to `http://<host-LAN-IP>:3000/login`. The API (`:8001`) stays loopback-only either way — the browser only ever talks to the web server's same-origin proxy (`app/api/v1/[[...path]]/route.ts` → `127.0.0.1:8001`), so this doesn't widen exposure beyond the one port.
5. **Untested risk:** office Wi-Fi often enables **client isolation** (AP-level), which stops device-to-device traffic on the same SSID even with the firewall rule open and the right IP. If LAN colleagues can't connect despite steps 1–4, this is the next thing to check with IT — it can only be fixed on the network side, not from this machine.

## N. Outbound TCP 7844 blocked on some networks

Symptom: cloudflared's log repeats, with exponential backoff, something like:
```
ERR Unable to establish connection with Cloudflare edge error="DialContext error: dial tcp <edge-ip>:7844: i/o timeout"
```
across multiple edge IPs, and the connectivity pre-check block (visible on the next `cloudflared tunnel --url ...` start) shows `TCP Connectivity … FAIL`.

How this was diagnosed (2026-09-22, one network in this pilot): DNS resolution to the tunnel hostname succeeded; a raw TCP probe to the same edge IP on **port 443 succeeded**; a 6-hop traceroute to the edge IP completed normally; no VPN client process was running. That isolates the failure to **port 7844 specifically** being blocked by that network's firewall — not a DNS issue, not a general egress block, not a VPN artifact. A second network passed every cloudflared pre-check (DNS, QUIC, HTTP/2, Cloudflare API) and connected cleanly on the first try.

This is a separate, independent blocker from the managed-Chrome `*.trycloudflare.com` policy in §H — a network can block the tunnel port even for a browser that has no domain policy at all, and a browser can block the domain even on a network that allows the port. There is no workaround from this machine for a port-7844 block; it needs the network operator to allow it, or use §M's LAN-direct path instead when the tester is on the same network as the host.
