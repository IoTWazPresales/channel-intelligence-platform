# CURRENT state

**Last updated:** 2026-08-09 (handover: commit residuals; Unit E VERIFY next)

**Branch:** `feat/p4-cst-six-customer-shapes` (from `main` after PR #25 merge `9bbb318`)

**Alembic on cip:** `20260808_0011` (head)

## Locked CST product rule

Unmappable CST product → **Ignore** (`ignore_no_catalogue`) → catalogue gaps (`source=cst`). Never auto-create PM. FLAG ≠ BLOCK.

## Locked Game framing (Warren)

Game 2026 is **NOT** a new layout/schema/`structure_type`. Steward column mapping is the product model. Fix header detection / `dual_header_merge` so real labels (or stable `col_N`) reach the steward map.

## P4 + agent-safe follow-ons (proven)

| Item | Proof |
|---|---|
| Generic unit↔total | `customer_sell_through_measures.py` + Amazon/Game jobs |
| HiFi/IC Chain split | jobs **912/913** |
| CM `mtd_delta` | **916→917** (106/111 prior deltas) |
| Native `.xls` CST reader | xlrd in `_read_workbook_sheets`; OLE Microman fixture sheet open; template accepts `.xls` |
| Listing seeds (generic) | `feed_profile.listing_seed`; Amazon job **918** → **51** `cst_listing_seed` rows (`marketplace=amazon`) |
| CST validate `on_progress` | pipeline forwards; job 918 progress events parsing + resolving |
| Evetech multi-week soak | jobs **919/920** validated |
| Unit E CST steward (browser) | job **911**: Products(0) / Locations(52 needs work); chip filters; plan toolbar; FLAG≠BLOCK sites — formal S1–S14 consult VERIFY not stamped |
| Game Week 33 dual_header | works |
| Game Asus Sales W27/W29/W30 | jobs **921–923** FAILED — headers → `col_0..` + Fiscal Week / Sales U TY (EAN/UPC not surfaced) → product unmapped |

**Local note:** `admin@local` password = seed `changeme` for browser smoke.

## Next (in order)

1. Unit E CST steward formal VERIFY via consult (PASS/STOP)
2. Game header surfacing + steward column-map path (no new layout family)
3. P5 live fetch + auto-finder (`CIP_LISTING_LIVE_FETCH` + schedule; do not gate on 2 weeks of observations)
4. Optional later: 068 lens, 076 purge (~17 unship), 089/092, P6 after public deploy

**Env:** local Windows. `cip` @ `20260808_0011`.
