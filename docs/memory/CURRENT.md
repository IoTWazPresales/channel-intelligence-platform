# CURRENT state

**Last updated:** 2026-08-01 (P2-3d admin users UI)
**Branch:** `feat/p2-auth-rbac` (pushed through P2-3c; P2-3d committing)
**Alembic:** `20260801_0003` on cip (IAM)

## Done

- PR #10 → main @ `9906b17`
- **P2-3 identity** `6956edf` — session login, roles, seed admin
- **P2-3b** `f818a1f` — AppShell session user + logout
- **P2-3c** `dfbbe83` — nav role gating (admin/steward/planner/viewer)
- Soak earlier: case #46 reapproval @ `MONEY_CEILING_USD=1`

## In progress / next

- **P2-3d:** Admin Users page + `GET /auth/users` (create via existing POST)
- Remaining P2-3: steward audit log; fact `tenant_id` isolation (needs migration approval)
- P2-4 shell/landing freshness; P2-5 monitoring (later)
- **X-1 CST Unit E VERIFY** (prefer new chat)

**Env:** local Windows. API `:8001` session mode, web `:3000`. Seed `admin@local` / `changeme`.
