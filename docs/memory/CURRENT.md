# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1–R1d; main `9ec8b63` merged in)

**Branch:** `feat/rbac-r1-session-actor` — flip this line back to `main` when this branch is merged.

**Last content pin:** `44530a4` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`) — in tree via merge of main. R1–R1d authored no revision.

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

**Alembic on cip_test:** `20260818_0018` (OWNER cip). R1d e2e wrote only here.

## On this branch

- Merged `origin/main` @ `9ec8b63` (shipping-mailer `0019` + API test pin `CIP_AUTH_MODE=stub` in conftest). Shipping-mailer is no longer a migration blocker.
- **R1 + R1b:** CPOR writes authenticate; actor from `user["id"]`. Historical-import header admin gate removed; CPOR stays authentication-only until R2.
- **R1c:** 41 non-CPOR `X-User-Role` gates → `Depends(require_roles(Role.ADMIN))`.
- **R1d:** 401 from web `api*` helpers clears the stored token and routes to `/login`. Payment-evidence actor from `_actor(_user)` (R1 helper); zero CPOR `X-User-*` Header params. Session e2e on cip_test: login then one swept route per of the five R1c routers — 200 admin / 403 viewer / 401 anon.
- Code default `cip_auth_mode` remains `"stub"`. Warren's `.env` is `session` (untouched). Conftest `setdefault` pins stub for pytest; explicit process `CIP_AUTH_MODE=session` still wins for R1d.

## FLAG

- CPOR routes remain authentication-only (no `require_roles`) until R2.
- Shipment steward panel is ADMIN-only (BACKLOG-141).
- `X-User-Id` actor stamps remain on CST / listing / lineup / promo / product-master-gaps (R3).
- `test_cpor_cases_api.py` / `test_cpor_historical_unit_c.py` do **not** prove HTTP `/apply` against Postgres.
- BACKLOG-144: `cip_test` lacks fixtures for lineup distributor-as-customer remediation tests.

## Next

1. Merge `feat/rbac-r1-session-actor` → main when GATE 3 passes (then flip Branch to `main` and close the RBAC program at R1–R1d).
2. R2: role-enforcement CONSULT (BACKLOG-136 / BACKLOG-141). Do not invent Role enum values.
3. Ops leftovers: BACKLOG-143 (amend: `cip_test` is real test infra — do not drop). Then steward + CPOR queue depth.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
