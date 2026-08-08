# CURRENT state

**Last updated:** 2026-08-08 (B4 promo draft on `feat/b4-promo-draft`)

**Branch:** `feat/b4-promo-draft` (from `feat/b2-author-loop` / PR #23)

**Alembic:** `20260807_0010` — no new migration

## Done

- **B2 trusted (browser):** budget `reservation_source=derived_from_profit` + builder-economics reservation + XLSX export PASS.
- **B4-01:** promo-plan-draft uses B2 lineup-derived budget; `POST …/create-case` writes draft CPOR case; `/promotions` UI create CTA; semantics IMPLEMENTED.

## Outstanding

| Item | Notes |
|------|--------|
| **PR #23** | B2 author loop — merge first (or with #24 stack) |
| **PR #24** | B4 promo draft — base `feat/b2-author-loop` |
| Parked A-lane | 068 / 089 / 092 / 097 |

## Next

1. Merge **PR #23** then **PR #24** when you say merge (or retarget #24 → main after #23 lands).
2. Lane X / parked TRIGGER.

**Env:** local Windows. `cip` @ `20260807_0010`.
