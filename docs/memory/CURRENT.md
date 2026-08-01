# CURRENT state

**Last updated:** 2026-08-01 (P3-1 complete for this branch; stop before P3-2)
**Branch:** `feat/p2-auth-rbac` @ `2fe8f5f`
**Alembic:** `20260801_0005` on cip

## Done this session

- **P2 residual tenant filters** — dim/sellout/shipping/channel-ops/CST/inbound + forecasts + inventory/customer + channel-ops inventory derived stock; apply writers stamp `tenant_id` from ImportJob
- **P3-1 Semantic layer** — full IMPLEMENTED catalog from COMMERCIAL_SEMANTICS; grain validity; tenant overlay path `catalog/tenants/{tenant_id}.yaml`; API `/semantics/*`
- **Not done (by design):** P3-2 query engine / report builder / dashboards

## Next (new chat)

1. **P3-2 Query engine** (metric+dim→SQL) when Warren starts it
2. Open PR for `feat/p2-auth-rbac` when ready (not yet)
3. **X-1 CST Unit E VERIFY** (prefer dedicated chat)

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
