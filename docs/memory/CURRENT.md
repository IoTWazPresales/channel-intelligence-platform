# CURRENT state

**Last updated:** 2026-08-20 (RBAC R1 on `feat/rbac-r1-session-actor`)

**Branch:** `feat/rbac-r1-session-actor`

**Last content pin:** `4ea1782` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On this branch

- **RBAC R1 (BACKLOG-136 slice):** CPOR write routes take `Depends(get_current_user)`. `_actor()` is `user["id"]` (non-null). Event `payload_json` gets `actor_email` / `actor_role`. No `X-User-Id` Header on `cpor_cases` / `cpor_exports`. Web: `authHeaders()` exported; forged `X-User-*` literals removed from `apps/web/src`. Code default `cip_auth_mode` remains `"stub"`. No migration, no Role enum change, no `require_roles`.
- Structural test: `apps/api/tests/test_cpor_rbac_r1_auth.py` (no DB).

## FLAG (in-scope consequence)

Historical import **GET** routes still call `_require_admin(X-User-Role)` (`profiles`, `summary`, `candidates`, `progress`). R1 must not auth GET routes. After forged-header removal those GETs **403** unless the client still sends `X-User-Role` (it must not). Payment-evidence GETs already use `get_current_user` and are fine.

## Next

R2: role enforcement (`require_roles`, KAM/PM/Ken/Wayne mapping) — CONSULT first. Or a follow-up that authenticates historical-import **GET**s the same way as writes (out of R1). Settlement / MAC / line-windows still not started.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
