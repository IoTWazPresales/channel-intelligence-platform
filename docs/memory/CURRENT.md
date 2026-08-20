# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1c on `feat/rbac-r1-session-actor`)

**Branch:** `feat/rbac-r1-session-actor`

**Last content pin:** `0f88e1d` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`) — no new revision in R1c

**Alembic on cip_test:** `20260818_0018` (created this unit, OWNER cip)

**Alembic on cip:** `20260818_0019` — **ahead of this branch's files** (no `0019` revision in the tree). R1c only `SELECT`ed cip; it did not migrate cip. Investigate before any cip upgrade.

## On this branch

- **RBAC R1 + R1b:** CPOR writes authenticate via `get_current_user`; actor from `user["id"]`. Historical-import header admin gate removed; CPOR stays authentication-only until R2.
- **RBAC R1c:** 41 non-CPOR `X-User-Role` 403 gates replaced with `Depends(require_roles(Role.ADMIN))` — `shipment_evidence.py` 25, `mappings.py` 7, `imports_product_master.py` 5, `products.py` 2, `imports.py` 2. Three import template/source GETs filter on session `user["role"]`. No CPOR router change. No Role widening to STEWARD.
- Structural tests: `test_cpor_rbac_r1_auth.py`, `test_rbac_r1c_admin_gates.py`.
- Code default `cip_auth_mode` remains `"stub"`.

## FLAG

- CPOR routes remain authentication-only (no `require_roles`) until R2.
- Shipment steward panel is ADMIN-only (BACKLOG-141).
- `X-User-Id` actor stamps remain on CST / listing / lineup / promo / product-master-gaps (R3). `cpor_payment_evidence.py` still has unaliased `Header()` `x_user_id` (CPOR — not touched).
- `test_cpor_cases_api.py` / `test_cpor_historical_unit_c.py` PASS on cip_test but are mocked / SQLite — they do **not** prove HTTP `/apply` against Postgres.
- Bulk-delete mutating tests skipped on empty cip_test (no dim rows). Auth-only preview 403 test passed.

## Next

R2: role enforcement CONSULT. BACKLOG-141 (STEWARD on steward panels). Do not migrate cip onto an unknown `0019`.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
