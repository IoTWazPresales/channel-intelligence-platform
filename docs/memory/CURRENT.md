# CURRENT state

**Last updated:** 2026-08-08 (roadmap completion Waves 0–4 + Lane X 076)

**Branch:** `feat/cst-takealot-pilot-config` · **PR:** [#25](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/25) (await Warren promote)

**Alembic:** `20260807_0010` (authored not applied: `20260808_0011` listing tables IF NOT EXISTS — needs Warren approve)

## Locked CST product rule

Unmappable CST product → **Ignore** (`ignore_no_catalogue`) → catalogue gaps (`source=cst`). Never auto-create PM. FLAG ≠ BLOCK.

## Demo gate checklist (2026-08-08)

| # | Gate | Result |
|---|------|--------|
| 1 | Login → dashboard | PASS (`admin@local` → `/dashboard`; forgot-password copy + Admin reset) |
| 2 | Weekly CST loads | Takealot path proven (job 799); operator = Import Centre CST batch |
| 3 | Scheduled report → inbox | BACKLOG-098 closed (code + schedule id=1 last_run); `/inbox` loads with vintage copy |
| 4 | Lineup / 5 Promo / 6 PvE | Surfaces on main; prior unit smokes stand (no rebuild) |
| 076 | Amount-scale junk | Mitigated — KPI excludes unit_price > 100k (17 unship rows on cip) |

## Shipped this completion pass

- Wave 0: CST batch browser smoke; PR #25; VERIFY waived
- Wave 1: admin set-password; 076 KPI exclusion; 098 closed
- Wave 2: P4 bootstrap 7 customer_report_config placeholders (Evetech…Game) awaiting sample files
- Wave 3: `20260808_0011` authored; live fetch behind `CIP_LISTING_LIVE_FETCH` + schedule env
- Wave 4: tenant profile Settings UI (BACKLOG-096); backup dump + restore smoke → `cip_alembic_smoke` PASS
- Historical CST: **deferred** until after promote + one live weekly apply (roadmap forward-first)

## Next

1. Warren: **promote/merge PR #25**
2. Warren: approve `alembic upgrade` for `20260808_0011` (safe IF NOT EXISTS on cip)
3. Sample WEEK files for remaining P4 customers → structure discovery (Q-004)
4. Optional CST historical backfill after weekly soak

**Env:** local Windows. `cip` @ `20260807_0010`. Takealot=20. Q-003 hosting still deferred.
