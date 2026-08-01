# CURRENT state

**Last updated:** 2026-08-01 (P2-3d pushed)
**Branch:** `feat/p2-auth-rbac` @ `7777dae` (in sync with origin)
**Alembic:** `20260801_0003` on cip (IAM)

## Done

- PR #10 → main @ `9906b17`
- **P2-3** through **P2-3d** on `feat/p2-auth-rbac`:
  - `6956edf` identity (login/sessions/roles/seed)
  - `f818a1f` AppShell session user + logout
  - `dfbbe83` nav role gating
  - `7777dae` Admin Users page + `GET /auth/users`
- Soak earlier: case #46 reapproval @ `MONEY_CEILING_USD=1`

## Not done / next

- P2-3 remainder: **steward audit** log; **fact `tenant_id` isolation** (needs migration approval)
- P2-4 shell/landing; P2-5 monitoring
- **X-1 CST Unit E VERIFY** (prefer new chat)
- Browser smoke of P2-3b–d on running stack (web was down during this session)

**Env:** local Windows. API `:8001` session mode, web `:3000`. Seed `admin@local` / `changeme`.
