# N-0033 verification record — session gate, production web, quick tunnel

**Run:** `STAGE3_ACCESS_20260921` · **Actor:** `stage3-001` · **Date:** 2026-09-21 · **Baseline:** `BLN-0004` @ `ff118ec`
**Commits:** `26a6e1a` (router-level gate + `tests/test_session_gate.py`); test repairs + conftest shim in the commit that follows this record. Passwords were set by Warren via `Invoke-RestMethod` before the mode flip — never seen or sent by the agent.

## 1. Live route enumeration (`GET`, no token, `CIP_AUTH_MODE=session`)

| State | Routes tested | 200 without token | 401/403 |
|---|---|---|---|
| Before gate (per-endpoint auth) | 207 | **127** | 35 |
| After gate, live API restarted | 207 | **0** | **207** |

Method: `openapi.json` from `:8001`, every GET path with path params sampled (`{case_id}`→46, `{job_id}`→605, ids→1), `/health` and `/auth/login` excluded. The first post-gate enumeration still showed 127 because uvicorn's reloader had **not** picked up the edits; an explicit restart was required. Also verified: wrong-password `POST /auth/login` → 401 (route reachable, ungated); forged `X-User-Role: admin` + `X-User-Id: 1` → 401; `GET /dev/database-wipe` → 401.

Design: `api_router = APIRouter(dependencies=[Depends(get_current_user)])`; `/auth/login` moved to `auth.public_router`, mounted without the dependency; `/health` stays on the app. Stub mode unaffected by construction (`get_current_user` never raises in stub).

## 2. Tests

- `tests/test_session_gate.py` — 4 tests: sampled previously-open routes → 401; forged headers → 401; login reachable (401 not 404) + `/health` 200; stub mode still 200. Green with `test_health` + `test_market_placeholders` (9/9).
- Full suite: the first run (`-x`) stopped at `test_create_commercial_plan_contract` — the gate now awaits a `MagicMock` session in ~21 contract-test files that override `get_db`. Fixed with an autouse conftest shim that short-circuits `_resolve_stub_app_user` **only** for non-`AsyncSession` sessions (returns the stub's admin@local); real sessions and session mode untouched. Two further failures (`test_lineup_coverage_*`) were **pre-existing since `8ff8dc6`** (12-tuple fixtures vs a 13-column select) and hidden behind `-x`; fixtures repaired. `test_commercial_planner_api.py` 81/81. Full-suite count: see §5.

## 3. Web

`apps/web/.next` was corrupted when `next build` ran while `next dev` was still up (my sequencing): `next start` found no `BUILD_ID`, and the restarted dev server 404'd `/login`. Fixed by stopping dev, `rm -rf .next`, clean `pnpm --filter @cip/web build` (✓ 72s, `BUILD_ID NFPNN0ilA-rxf1io1wAyO`), then `next start -H 127.0.0.1 -p 3000` (the package `start` script binds `0.0.0.0`; overridden to loopback). Local: `/login` 200, `/api/v1/auth/me` via proxy 401, `/` 307.

`next build` also surfaced a latent TS2344 in `.next/types` for `shipping/page.tsx` (page module exporting a component); fixed in `21f242e` by moving `InboundShipmentsWorkspace` to `features/supply-inbound/` with aliased sibling imports.

## 4. Tunnel

cloudflared **2026.9.1** from the official GitHub release (`winget` is not on any tool-shell PATH here; a winget process launched via its App Execution Alias hung for 15 minutes and was stopped). First run on QUIC registered but requests from this machine returned `000`/intermittent; restarted with `--protocol http2`:

**https://letter-closes-cia-norman.trycloudflare.com** (changes on every restart)

| Path | Result |
|---|---|
| `/login` | **200**, `Server: cloudflare`, `CF-Ray …-JNB` |
| `/api/v1/auth/me` (no token) | **401** |
| `/api/v1/customers?page=1&page_size=1` (no token) | **401** |
| `/docs` | **404** — `:8001` is not fronted |

Warren's managed Chrome blocks `*.trycloudflare.com` by organisation policy (Chrome: "This site is blocked by your organization's policy"), so the external test must come from a phone on mobile data or an unmanaged browser.

## 5. Full API suite

Pending at the time of writing this record — running in the background without `-x`; result appended to the commit message of the test-repair commit and to CURRENT.md.

## 6. Independence and limits

`verification.referent` is independence-required (R3). This record is implementation-side. Browser-level authenticated smoke through the tunnel was not possible from this session (agent does not handle passwords; Warren's Chrome is policy-blocked).
