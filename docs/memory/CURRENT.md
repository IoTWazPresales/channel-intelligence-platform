# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1b on `feat/rbac-r1-session-actor`)

**Branch:** `feat/rbac-r1-session-actor`

**Last content pin:** `4ea1782` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On this branch

- **RBAC R1 + R1b (BACKLOG-136 slice):** CPOR writes authenticate via `get_current_user`; actor from `user["id"]`. Historical-import `_require_admin(X-User-Role)` removed; GETs and POSTs authenticate only. Web forged `X-User-*` literals gone. Code default `cip_auth_mode` remains `"stub"`. No migration, no Role enum, no `require_roles`.
- Structural test: `apps/api/tests/test_cpor_rbac_r1_auth.py` (no DB). `cip_test` does **not** exist — write-capable CPOR tests not run.

## FLAG (closed by R1b)

Historical-import GETs now use `Depends(get_current_user)`. `_require_admin(X-User-Role)` is gone from `cpor_historical_import.py`. Authorization on those 11 routes is authentication-only until R2.

## Next

R2: role enforcement (`require_roles`, KAM/PM/Ken/Wayne mapping) — CONSULT first. Restore a stronger check on historical-import writes (validate/apply/resolution-plan). Settlement / MAC / line-windows still not started.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
