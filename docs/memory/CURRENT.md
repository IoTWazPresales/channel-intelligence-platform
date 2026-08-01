# CURRENT state

**Last updated:** 2026-08-01 (P2-3d browser smoke PASS)
**Branch:** `feat/p2-auth-rbac` @ `6c4d1cf` (in sync with origin)
**Alembic:** `20260801_0003` on cip (IAM)

## Done

- PR #10 → main @ `9906b17`
- **P2-3 → P2-3d** on `feat/p2-auth-rbac` (each step committed+pushed):
  - `6956edf` identity (login/sessions/roles/seed)
  - `f818a1f` AppShell session user + logout
  - `dfbbe83` nav role gating
  - `7777dae` Admin Users + `GET /auth/users`
  - `6c4d1cf` CURRENT pin
- **Browser smoke PASS** (API restarted session mode): Local Admin in shell; Users table; created `viewer@local`

## Not done / next (needs Warren pick)

1. **Steward audit** log (P2-3 remainder)
2. **Fact `tenant_id` isolation** — requires **migration approval**
3. P2-4 shell/landing · P2-5 monitoring
4. **X-1 CST Unit E VERIFY** (prefer new chat)

**Env:** local Windows. API `:8001` (`CIP_AUTH_MODE=session`), web `:3000`. Seed `admin@local` / `changeme`.
