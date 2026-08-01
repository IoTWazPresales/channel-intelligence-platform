# CURRENT state

**Last updated:** 2026-08-01 (P2-3 IAM applied + login smoke)
**Branch:** `feat/p2-auth-rbac` (uncommitted P2-3 work)
**Alembic:** `20260801_0003` on cip (IAM)

## Done

- PR #10 → main @ `9906b17`
- **P2-3 identity slice live on cip:** migration applied; seed `admin@local` / `changeme`; `CIP_AUTH_MODE=session`
- Browser login smoke PASS → `/dashboard` with Bearer token stored
- Soak earlier: case #46 reapproval chip/banner + export 409 (`MONEY_CEILING_USD=1`)

## Not done / next

- **X-1 CST Unit E VERIFY** (prefer new chat — handover prompt ready)
- P2 remainder: AppShell still shows `demo-user` label; nav role gating; admin create-user UI; steward audit; fact `tenant_id` isolation
- Commit/push `feat/p2-auth-rbac` when Warren asks

**Env:** local Windows. API on `:8001` (no-reload session mode), web `:3000`. Change seed password after first use.
