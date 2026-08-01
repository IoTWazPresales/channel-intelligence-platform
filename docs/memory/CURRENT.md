# CURRENT state

**Last updated:** 2026-08-01 (P2-3b AppShell session user)
**Branch:** `feat/p2-auth-rbac` @ `6956edf`+ (P2-3b in flight)
**Alembic:** `20260801_0003` on cip (IAM)

## Done

- PR #10 → main @ `9906b17`
- **P2-3 identity** committed+pushed `6956edf` (session login, roles, seed admin)
- Soak earlier: case #46 reapproval chip/banner + export 409 (`MONEY_CEILING_USD=1`)

## In progress

- **P2-3b:** AppShell shows `/auth/me` user (not demo-user); logout; Bearer-only headers when token present

## Not done / next

- P2 remainder: nav role gating; admin create-user UI; steward audit; fact `tenant_id` isolation
- **X-1 CST Unit E VERIFY** (prefer new chat)

**Env:** local Windows. API on `:8001` (no-reload session mode), web `:3000`. Seed `admin@local` / `changeme`.
