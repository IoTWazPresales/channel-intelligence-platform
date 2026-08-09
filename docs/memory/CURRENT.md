# CURRENT state

**Last updated:** 2026-08-09 (P5 registry populated + observation soak)

**Branch:** `feat/p4-cst-six-customer-shapes` (pushed)

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game 2026 ≠ new structure_type — steward column map + header fix only.
- P5: enable live fetch now; ≥2 weeks obs gate is for **intelligence v1** only.

## Proven this branch

| Item | Proof |
|---|---|
| P4 / Unit E / Game headers | prior commits |
| P5 auto-finder + live fetch | `bfd0c44` + follow-on |
| Amazon seeds → registry | **51** `customer_listing` (feed_proposal); proposed queue **0** |
| Observation soak | poll **51** listings → **52** obs, all http **200** / parse **ok** |
| Browser | `/listing-capture` Registry amazon rows; Feed proposals shows **Confirm all suggested URLs**; empty after confirm |

**Local:** `.env` has `CIP_LISTING_LIVE_FETCH=1`, `CIP_LISTING_CAPTURE_SCHEDULE=1`, `CIP_ENABLE_DEV_BEAT=1`. API restarted this session. Run `pnpm dev:worker` (with beat) for recurring polls.

## Next

1. Keep worker+beat running so history accrues toward intelligence v1
2. Optional: wide-week unpivot, 068/076/089/092, P6, PR merge when Warren asks

**Env:** local Windows. `cip` @ `20260808_0011`.
