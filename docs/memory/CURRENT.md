# CURRENT state

**Last updated:** 2026-08-01 (P2-3e applied + smoke PASS)
**Branch:** `feat/p2-auth-rbac` @ `0cd2225`+
**Alembic:** `20260801_0004` on cip (steward_audit_event)

## Done

- P2-3 → P2-3d identity/shell/nav/users (smoke PASS)
- **P2-3e steward audit live:** `20260801_0004` applied on cip; `GET /admin/steward-audit` shows smoke row (Local Admin / dsi / P2-3e-SMOKE); DSI write hooks wired

## Not done / next

1. Optional: wire shipment/CPOR/CST to same `record_steward_audit`
2. **Fact `tenant_id` isolation** — needs separate migration approval
3. P2-4 shell/landing · P2-5 monitoring
4. **X-1 CST Unit E VERIFY** (prefer new chat)
5. Open PR for `feat/p2-auth-rbac` when ready

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
