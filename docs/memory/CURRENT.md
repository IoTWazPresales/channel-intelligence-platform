# CURRENT state

**Last updated:** 2026-08-08 (PR #22 merged — A-lane residual close-out)

**Branch:** `main` @ `120e020` (merge of `feat/a-lane-residual-closeout`)

**Alembic:** `20260807_0010` — no new migration

## Done

- **PR #18–#22 MERGED** (Unit 6c+6f through A-lane residual).
- A1-09 support bias + BACKLOG-093 Promo load on main.
- A2/A3 VERIFY PASS.

## Outstanding (parked)

| ID | Topic | TRIGGER |
|----|--------|---------|
| **068** | PvE Landed tile / shipped-not-landed | Shipping scopes it or transit gap material |
| **089** | Incremental promo unit cost | Validated baseline model |
| **092** | Paid vs owed (Ken payments) | Warren supplies payment files |
| **097** | A3/P3 cold-query perf | Soak says p95 still slow |

Also: seed `commercial_sku_assumption` so A1-09 bias % is computable; load CST so Promo load has real buckets (not just `no_cst`).

## Next

1. **B2** — lineup + budget builder (net requirement, profit/reservation, budget position), **or**
2. **Lane X** continuous (TMP-CUST / steward retrofit), **or**
3. Fire a parked TRIGGER above.

**Env:** local Windows. `cip` @ `20260807_0010`.
