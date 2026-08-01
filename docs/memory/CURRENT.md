# CURRENT state

**Last updated:** 2026-08-01 (P2-3g tenant_id applied + smoke PASS)
**Branch:** `feat/p2-auth-rbac` @ `bea77a8`
**Alembic:** `20260801_0005` on cip (tenant_id on core facts/dims)

## Done

- P2-3 → P2-3d identity/shell/nav/users (smoke PASS)
- P2-3e steward audit live (`20260801_0004`) — DSI + admin UI
- **P2-3f** steward audit on shipment / CPOR historical / CST writes
- **P2-3g tenant_id MVP:** migration `20260801_0005` applied on cip; columns on facts/dims/import_job/cpor_case; `tenant_scope` helpers; CPOR list/get/create scoped. Browser: CPOR Cases grid loads (297 default-tenant); steward audit smoke row still visible

## Not done / next

1. Broader tenant filters on more read/write paths (DSI/shipment/CST lists) — columns exist; not all endpoints filter yet
2. P2-4 shell/landing · P2-5 monitoring
3. **X-1 CST Unit E VERIFY** (prefer new chat)
4. Open PR for `feat/p2-auth-rbac` when ready

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
