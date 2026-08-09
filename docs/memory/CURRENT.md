# CURRENT state

**Last updated:** 2026-08-09 (Game header surfacing fix)

**Branch:** `feat/p4-cst-six-customer-shapes` (pushed)

**Alembic on cip:** `20260808_0011` (head)

## Locked CST product rule

Unmappable CST product → **Ignore** (`ignore_no_catalogue`) → catalogue gaps (`source=cst`). Never auto-create PM. FLAG ≠ BLOCK.

## Locked Game framing (Warren)

Game 2026 is **NOT** a new layout/schema/`structure_type`. Steward column mapping is the product model. Fix header detection / `dual_header_merge` so real labels (or stable `col_N`) reach the steward map.

## Proven this branch

| Item | Proof |
|---|---|
| P4 residuals | commit `69f64fa` — measures, .xls, listing seeds, validate progress |
| Unit E CST steward | **VERIFY PASS** Opus S1–S14 (`9e94606`) |
| Game header surfacing | distinct-canon header score + weak `EA` + period-band dedupe; jobs **921/922/923** → validated (75/60/121 rows); Week 33 still merges ZAR→Sales R TY |
| Stale CST parse error clear | successful re-validate pops `customer_sellthrough_error` |

**Local note:** `admin@local` / `changeme` for smoke.

## Next (in order)

1. P5 live fetch + auto-finder (`CIP_LISTING_LIVE_FETCH` + schedule; do not gate on 2 weeks of observations)
2. Optional later: wide-week unpivot (skipped earlier-week-only rows), 068 lens, 076 purge, 089/092, P6 after public deploy

**Env:** local Windows. `cip` @ `20260808_0011`.
