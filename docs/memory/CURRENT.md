# CURRENT state

**Last updated:** 2026-08-01 (P2 residual tenant filters — in progress commit)
**Branch:** `feat/p2-auth-rbac` @ (pending push)
**Alembic:** `20260801_0005` on cip

## Done (P2 usable-by-others)

- **P2-1 Deployment** — deferred (no hosting target)
- **P2-2 Alembic replayability** — DONE (squash baseline)
- **P2-3 Auth + RBAC** — session login, roles, users, steward audit, tenant_id MVP + CPOR scope
- **P2-3 residual** — broader tenant filters on dim/sellout/shipping/channel-ops/CST list reads; apply writers stamp `tenant_id` from `ImportJob`
- **P2-4 App shell + landing** — Control tower freshness banner + shortcuts; getting-started session copy (browser PASS)
- **P2-5 Monitoring + backup/DR** — `/health` + `/health/ready`; `/admin/ops` failed-job board; `docs/BACKUP_AND_DR.md`; backup + restore smoke into `cip_alembic_smoke`

## Not done / next

1. **P3-1 Semantic layer** (governed metrics registry — not PowerBI) — start next
2. Open PR for `feat/p2-auth-rbac` when ready (Warren: not yet)
3. Remaining tenant gaps (P1): channel-ops inventory derived stock internals, forecasts list, inventory/customer — columns exist; default tenant still safe
4. **X-1 CST Unit E VERIFY** (prefer new chat)

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
