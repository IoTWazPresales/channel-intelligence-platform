# CURRENT state

**Last updated:** 2026-08-08 (PR #23 + #24 on main — B2 author loop + B4 promo draft)

**Branch:** `main` @ `03043d4`

**Alembic:** `20260807_0010` — no new migration this ship

## Done

- **PR #23 MERGED** — B2 Units 1–3 author loop (SRP fix, Apply, half-year/bias, XLSX, commercial case write)
- **PR #24 MERGED** — B4-01 promo draft compose + create-case (lineup-derived budget); browser smoke case #300
- B-lane core (B1–B4) scaffold + author/create paths now on main

## Outstanding

| Item | Notes |
|------|--------|
| **CI tip assert** | Workflow still asserts alembic `20260802_0009`; real head `20260807_0010` — fix CI pin (unrelated to B2/B4) |
| **Full ASUS workbook column parity** | Only if tenant rejects XLSX on-ramp |
| **BACKLOG-068** | PvE Landed tile — Shipping TRIGGER |
| **BACKLOG-089** | Incremental promo unit cost |
| **BACKLOG-092** | Paid vs owed (Ken payments) |
| **BACKLOG-097** | A3/P3 cold-query perf |
| **BACKLOG-123** | Migrate promote/merge onto ResolutionWorklist |
| **Lane X** | Steward retrofit / TMP-CUST continuous |

Also: seed more `commercial_sku_assumption` so bias/% reservation covers more SKUs; load CST for Promo load buckets beyond empty-state.

## Next

1. Fix CI alembic tip assert → `20260807_0010`, **or**
2. Lane X / fire a parked TRIGGER above.

**Env:** local Windows. `cip` @ `20260807_0010`.
