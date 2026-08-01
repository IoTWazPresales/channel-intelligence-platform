# CURRENT state

**Last updated:** 2026-08-01 (P3-1 semantic layer scaffold)
**Branch:** `feat/p2-auth-rbac` @ (pending P3-1 push)
**Alembic:** `20260801_0005` on cip

## Done

- **P2** usable-by-others locally (P2-1 hosting deferred; P2-2→P2-5 + residual tenant filters)
- **P3-1 Semantic layer (scaffold)** — YAML metric/dimension registry + grain validity API
  - `GET /api/v1/semantics/catalog|metrics|dimensions`
  - `POST /api/v1/semantics/validate` refuses invalid metric×grain with explanation
  - Config: `apps/api/app/semantics/catalog/default.yaml` (from COMMERCIAL_SEMANTICS)
  - **Not** P3-2 query engine / report builder

## Not done / next

1. **Stop before P3-2+** (per session goal) — query engine is next phase when Warren asks
2. Expand catalog to full IMPLEMENTED metric set (A1-03..06, A1-08, A2-01/04/05, B1-02..)
3. Tenant overlay YAML path (config not code for tenant #2) — stub not wired yet
4. Open PR for `feat/p2-auth-rbac` when ready (Warren: not yet)
5. **X-1 CST Unit E VERIFY** (prefer new chat)
6. Remaining tenant P1: channel-ops inventory derived internals, forecasts list, inventory/customer

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
