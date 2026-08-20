# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1d on `feat/rbac-r1-session-actor`)

**Branch:** `feat/rbac-r1-session-actor` — flip this line back to `main` when this branch is merged.

**Last content pin:** `0f88e1d` — do not treat a hash in this file as HEAD (R1d commit is newer)

**Alembic (code on this branch):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`) — R1d authored no revision.

**Alembic on cip_test:** `20260818_0018` (OWNER cip). R1d e2e wrote only here.

**Alembic on cip:** `20260818_0019`. Explained: `apps/api/alembic/versions/20260818_0019_shipping_mailer_recipient.py` lives on `feat/shipping-mailer-recipients` (head `b5cf3a0`, **not** merged to `main`). Revises `20260818_0018`, chain clean, additive table `shipping_mailer_recipient`. Do not upgrade cip from this branch (file is not in the tree).

## On this branch

- **R1 + R1b:** CPOR writes authenticate; actor from `user["id"]`. Historical-import header admin gate removed; CPOR stays authentication-only until R2.
- **R1c:** 41 non-CPOR `X-User-Role` gates → `Depends(require_roles(Role.ADMIN))`.
- **R1d:** 401 from web `api*` helpers clears the stored token and routes to `/login`. Payment-evidence actor from `_actor(_user)` (R1 helper); zero CPOR `X-User-*` Header params. Session e2e on cip_test: login then one swept route per of the five R1c routers — 200 admin / 403 viewer / 401 anon.
- Code default `cip_auth_mode` remains `"stub"`. Warren's `.env` is `session` (untouched).

## FLAG

- CPOR routes remain authentication-only (no `require_roles`) until R2.
- Shipment steward panel is ADMIN-only (BACKLOG-141).
- `X-User-Id` actor stamps remain on CST / listing / lineup / promo / product-master-gaps (R3).
- `test_cpor_cases_api.py` / `test_cpor_historical_unit_c.py` do **not** prove HTTP `/apply` against Postgres.
- Promoting `feat/shipping-mailer-recipients` to main is a **BLOCKER on any new migration, including R2**.

## Next

1. Merge `feat/rbac-r1-session-actor` → main when Warren says promote (then flip Branch to `main`).
2. R2: role-enforcement CONSULT (BACKLOG-136 / BACKLOG-141). Do not author a migration until the shipping-mailer branch is on main (or 0019 is otherwise in the chain).
3. Ops leftovers: BACKLOG-143.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
