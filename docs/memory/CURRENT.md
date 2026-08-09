# CURRENT state

**Last updated:** 2026-08-09 (Unit E CST steward VERIFY PASS)

**Branch:** `feat/p4-cst-six-customer-shapes` @ `69f64fa` (pushed; tip may advance with this docs stamp)

**Alembic on cip:** `20260808_0011` (head)

## Locked CST product rule

Unmappable CST product → **Ignore** (`ignore_no_catalogue`) → catalogue gaps (`source=cst`). Never auto-create PM. FLAG ≠ BLOCK.

## Locked Game framing (Warren)

Game 2026 is **NOT** a new layout/schema/`structure_type`. Steward column mapping is the product model. Fix header detection / `dual_header_merge` so real labels (or stable `col_N`) reach the steward map.

## P4 + Unit E (proven)

| Item | Proof |
|---|---|
| Generic unit↔total | `customer_sell_through_measures.py` + Amazon/Game jobs |
| HiFi/IC Chain split | jobs **912/913** |
| CM `mtd_delta` | **916→917** |
| Native `.xls` CST reader | xlrd + template `.xls` |
| Listing seeds | Amazon **918** → **51** `cst_listing_seed` |
| CST validate `on_progress` | job 918 progress events |
| Evetech soak | **919/920** |
| **Unit E CST steward** | **VERIFY PASS** Opus 2026-08-09 — S1–S14 all PASS (`.tmp/unit_e_cst_steward_verify_opus_response.md`); prior X-1 PR #12; browser walk job **911** |
| Game Week 33 dual_header | works |
| Game Asus Sales W27/W29/W30 | jobs **921–923** FAILED — headers → `col_0..` + Fiscal Week / Sales U TY → product unmapped |

**Local note:** `admin@local` / `changeme` for smoke.

## Next (in order)

1. **Game header surfacing** + steward column-map path (no new layout family)
2. P5 live fetch + auto-finder (`CIP_LISTING_LIVE_FETCH` + schedule)
3. Optional later: 068 lens, 076 purge, 089/092, P6 after public deploy

**Env:** local Windows. `cip` @ `20260808_0011`.
