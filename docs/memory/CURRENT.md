# CURRENT state

**Last updated:** 2026-08-13 (P5 residual Takealot fetch)

**Branch:** `feat/p5-residual` (from `main` @ `4aa538a` / PR #37)

**Alembic on cip:** `20260812_0014`

## Arc progress

| Unit | Status |
|---|---|
| 8 Demo/P2 | **Merged** PR #36 → `main` |
| 11 Import parity | **Merged** PR #37 → `main` (`4aa538a`) |
| 12 P6 light | Export sheet Settings shipped in PR #37 — no further P6 this branch |
| 9–10 | Blocked (094 / 092) |
| P5 residual | **This branch** — Takealot REST fetch proven; BACKLOG-130 paths proven on historical windows |

## This branch

- Takealot poll uses `api.takealot.com/rest/v-1-16-0/product-details` (not the Next.js SPA shell)
- CST Product ID is a **SKU**, not a PLID; resolve via exact EAN (one hit + barcode/SKU corroboration)
- Price ← buybox selling `price`, never RRP `listing_price`
- Live cip poll: 21/24 Takealot `ok` with ZAR sell prices; 3 unlinked listings `parse_failed` (no product/EAN)
- BACKLOG-130: live poll still `no_case_detected` (no CPOR window covering today). Historical as_of on live prices: `price_consistent` (C26113297) and `not_activated` (C25B00340)

## Next

1. Warren uploads latest CPOR covering today, then re-poll for current-window activation
2. Restart API so the UI Poll button uses Takealot REST fetch
3. Link 3 Takealot listings that have no `product_id` (no EAN resolve)

**Env:** local Windows.
