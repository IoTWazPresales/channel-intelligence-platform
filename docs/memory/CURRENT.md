# CURRENT state

**Last updated:** 2026-08-17 (CST store grain + Amazon notebooks + P5 intel v1)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `1afdff4` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — do not upgrade unless approved

## On this branch

- P0–P3-1 / CST aliases / hygiene as previously pinned (`4effbb5` … `49ccec4`).
- **P4 Amazon (2026-08-17):** Job 918 **31 facts**. Notebooks `B0CND7JMYP`→11045 and `B0CZ97VQ4H`→5959 confirmed via shipping-as-of (aliases 685/686, FLAG SKU-twin). 19 networking ASINs `ignore_no_catalogue` (catalogue gap). SKU-twin propose `11ca581`. No `dim_product` create (18177).
- **Game W27:** leftover `850016147` ignored as catalogue gap (jobs 926/928/971). Store grain: CST `source_key` uses `site_label` when location is unmapped. Job **971: 564 facts / 1308 units** (matches staging). FLAG ≠ BLOCK on locations.
- **P5 intelligence v1:** `GET /listing-capture/intelligence` + Intelligence tab. ≥14d span → ready; else accumulating. `not_activated` worklist. Browser: rows show accumulating / span 0 (history still short).
- **BACKLOG-089:** `comparable_median` + `velocity_extrapolate` implemented; default remains `prior_window_same_sku_customer`.
- **BACKLOG-076:** quarantine complete (17 rows, 0 still-suspect). Source `Unit Price` is `999999`; Amount = Qty×999999. Do not re-import.
- **BACKLOG-098:** calendar runner due (schedule 1 since 2026-08-03). Unattended beat still off (`CIP_ENABLE_DEV_BEAT`). This Monday due-fire of WoC smoke hung >5 min — cancelled (097 cold path). Last successful inbox delivery remains `#4` sellout_units (2026-08-14).

## Last recorded test snapshot

Focused 2026-08-17: `test_incremental_unit_cost` + `test_listing_intelligence_v1` **6 passed**; CST foundation **26 passed** earlier this session. Do not treat the full API suite as green against live `cip`.

## Next

1. Do not start P6, Q-003 hosting, or Amazon historical weekly upload (Warren will upload).
2. BACKLOG-097 if Monday beat must deliver WoC at distributor×product (query currently exceeds proxy timeout).
3. Promote `feat/finish-roadmap` to main only when Warren says so — later-phase items remain (P6, hosting, 097, 098 overnight soak).

**Env:** local Windows. Web `:3000` + API `:8001` (restarted this session). No Docker.
