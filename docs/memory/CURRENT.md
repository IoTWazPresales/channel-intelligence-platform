# CURRENT state

**Last updated:** 2026-08-01 (P2 complete locally — P2-1 hosting deferred)
**Branch:** `feat/p2-auth-rbac` @ `638b5e5`
**Alembic:** `20260801_0005` on cip

## Done (P2 usable-by-others)

- **P2-1 Deployment** — deferred (no hosting target)
- **P2-2 Alembic replayability** — DONE (squash baseline)
- **P2-3 Auth + RBAC** — session login, roles, users, steward audit, tenant_id MVP + CPOR scope
- **P2-4 App shell + landing** — Control tower freshness banner + shortcuts; getting-started session copy (browser PASS)
- **P2-5 Monitoring + backup/DR** — `/health` + `/health/ready`; `/admin/ops` failed-job board; `docs/BACKUP_AND_DR.md`; backup + restore smoke into `cip_alembic_smoke` (`dim_product` 18168 = live)

## Not done / next

1. Open PR for `feat/p2-auth-rbac` when ready
2. Broader tenant filters beyond CPOR/import_job (columns exist)
3. **X-1 CST Unit E VERIFY** (prefer new chat)
4. **P3** analytics platform (new phase — not part of P2)

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
