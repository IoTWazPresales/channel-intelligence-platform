# CURRENT state

**Last updated:** 2026-08-17 (097 WoC observations + 098 catch-up)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `cce913b` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260817_0017` (`20260817_0017_weeks_of_cover_observation.py`)

**Alembic on cip:** `20260817_0017` (head) — applied 2026-08-17 (Warren approved)

## On this branch

- P0–P3-1 / CST aliases / hygiene as previously pinned (`4effbb5` … `49ccec4`).
- **P4 Amazon (2026-08-17):** Job 918 **31 facts**. Notebooks `B0CND7JMYP`→11045 and `B0CZ97VQ4H`→5959 confirmed via shipping-as-of (aliases 685/686, FLAG SKU-twin). 19 networking ASINs `ignore_no_catalogue` (catalogue gap). SKU-twin propose `11ca581`. No `dim_product` create (18177).
- **Game W27:** leftover `850016147` ignored as catalogue gap (jobs 926/928/971). Store grain: CST `source_key` uses `site_label` when location is unmapped. Job **971: 564 facts / 1308 units** (matches staging). FLAG ≠ BLOCK on locations.
- **P5 intelligence v1:** `GET /listing-capture/intelligence` + Intelligence tab. ≥14d span → ready; else accumulating. `not_activated` worklist. Browser: rows show accumulating / span 0 (history still short).
- **BACKLOG-089:** `comparable_median` + `velocity_extrapolate` implemented; default remains `prior_window_same_sku_customer`.
- **BACKLOG-076:** quarantine complete (17 rows, 0 still-suspect). Source `Unit Price` is `999999`; Amount = Qty×999999. Do not re-import.
- **BACKLOG-097:** `weeks_of_cover_observation` derived series. Apply-time reconstruct (DSI + shipment) + ops replay. Channel Ops / A3 / Monday schedule 1 read latest observation per pair. Live calculator only `woc_source=live` / `recompute=1`. **Proven:** reconstruct 10 distributors in ~21s (176982 rows / 2481 pairs); A3 query **0.61s**; inbox **#6** WoC smoke `status=ok value=23.68` `woc_source=observations`; Channel Ops Overview **61,776** / **23.7 weeks of cover**.
- **BACKLOG-098:** API lifespan poller claims overdue calendar schedules on startup + interval. Beat (when enabled) uses the same interval, not crontab 07:00-only. Claim-first; 90s statement timeout writes failed inbox. Does **not** require `CIP_ENABLE_DEV_BEAT`. **Proven this reconnect:** poller started then `reason=startup due_count: 0` (clock already at 2026-08-24 after the earlier catch-up). Inbox **#6** is the successful WoC delivery after 097.

## Last recorded test snapshot

Focused 2026-08-17: `test_woc_observation` + derived-stock + channel-ops + query-engine + tenant-profile + celery_queues + report_export **71 passed**. Live: Alembic `20260817_0017` on cip; Monday WoC delivery **#6** ok; API reconnect catch-up `due_count: 0`. Do not treat the full API suite as green against live `cip`.

## Next

1. Do not start P6, Q-003 hosting, or Amazon historical weekly upload (Warren will upload).
2. Promote `feat/finish-roadmap` to main (Warren authorized this session).

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker. 098 poller requires the API process.
