# CURRENT state

**Last updated:** 2026-08-08 (B2 Unit 1 author loop — in progress on feature branch)

**Branch:** `feat/b2-author-loop` (from `main` @ `3745cc0`)

**Alembic:** `20260807_0010` — no new migration

## Done this unit

- Fixed budget-position SRP: derive from commercial lineup `dap_evidence_local`/`msrp_local`; never `sku.target_srp_local`. Skip diagnostics `missing_sku` / `missing_srp`.
- `/lineup` Apply net-requirement CTA → draft `fact_lineup_plan_item`; builder-economics panel; budget caption shows `reservation_source=derived_from_profit`.
- COMMERCIAL_SEMANTICS §4.6 B2-01…04 marked **IMPLEMENTED** (CSV on-ramp caveat). ROADMAP B2 Unit 1 exit note.
- Browser VERIFY PASS on live cip: net req 50 pairs → Apply inserted 1647 drafts → budget lineup-derived after smoke SKU seed (3 products) → builder-economics reservation.

## Outstanding

| Item | Notes |
|------|--------|
| Commit / PR | When Warren asks |
| B2-2 | Richer authoring UX (period picker, bias toggle, half-year slots) |
| B2-3 | Tenant workbook export + commercial_lineup case write |
| Parked A-lane | 068 / 089 / 092 / 097 |

## Next

1. Commit + open PR for B2-1 when asked (do not merge without explicit merge).
2. Or B2-2 / Lane X / parked TRIGGER.

**Env:** local Windows. `cip` @ `20260807_0010`. Smoke SKUs seeded for products 5376/9908/10928 (dev only).
