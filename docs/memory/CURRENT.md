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
| **PR #23** | B2 author loop — still open; merge separately when asked |
| B4 commit/PR | This branch |
| Parked A-lane | 068 / 089 / 092 / 097 |

## Next

1. Browser smoke B4 on `/promotions` with seed case (e.g. 298).
2. Commit/PR for B4 when ready; merge only on explicit merge.

**Env:** local Windows. `cip` @ `20260807_0010`.
