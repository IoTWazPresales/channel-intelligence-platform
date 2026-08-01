# CURRENT state

**Last updated:** 2026-08-01 (P3-2 query engine v1; stop before P3-3)
**Branch:** `feat/p2-auth-rbac` @ `6aeadfb` (+ uncommitted P3-2)
**Alembic:** `20260801_0005` on cip

## Done this session

- **P3-2 Query engine** — `POST /api/v1/query/execute` + `/explain`; P3-1 `validate_metric_grain` gate; handlers reuse A3/A1/A2 owner services; process-local (+ optional Redis) 60s result cache
- **V1 metrics:** A3 stock/WoC/replenishment; A1 PvE scorecard family; A2 support_spend/delivery_rate/support_cost_per_unit_sold; others → `not_implemented`
- **Live cip:** WoC portfolio ≈13.6w (2481 pairs); fill_rate 26Q2 ≈0.465; cold ~5–7s, warm cache ≪1ms in-process; BACKLOG-097 for set-based/MV if cold NFR remains an issue
- **Not done (by design):** P3-3 report builder; PR not opened

## Next

1. **P3-3 Report builder** when Warren starts it (or BACKLOG-097 if cold query NFR is the priority)
2. Open PR for `feat/p2-auth-rbac` when ready (not yet)
3. **X-1 CST Unit E VERIFY** (prefer dedicated chat)

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
