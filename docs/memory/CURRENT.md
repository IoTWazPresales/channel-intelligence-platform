# CURRENT state

**Last updated:** 2026-08-13 (skip items verified in code; CURRENT pin → `edf29f3`)

**Branch:** `feat/p5-residual` (from `main` @ `4aa538a` / PR #37) @ `edf29f3` pushed (in sync with origin)

**Alembic on cip:** `20260812_0014`

## Arc progress

| Unit | Status |
|---|---|
| 8 Demo/P2 | **Merged** PR #36 → `main` |
| 11 Import parity | **Merged** PR #37 → `main` (`4aa538a`) |
| 12 P6 light | Export sheet Settings shipped in PR #37 |
| P5 residual | **Proven live** — Takealot REST + CPOR job 978 + today's activation flags |
| **13** | **Next** — BACKLOG-092 paid vs owed recon (TRIGGER fired) |
| **14** | Queued — BACKLOG-131 P3 widget canvas |
| **15** | Queued — B1 history forecast + BACKLOG-094 intake-weighted MAC + editable planner |
| P2 hosting | Stay local |
| P6 | Wait for a second company |

Plan: `.tmp/ARC_UNITS_13_15_PLAN.md`

## This branch

- Takealot poll uses REST product-details; SKU≠PLID; buybox sell price
- Listings **55–57** (Sheath II / Raikiri II / Keris II Origin) — no `dim_product`; CST barcodes ignored `ignore_no_catalogue`. `/admin/product-master-gaps` source=cst
- CPOR **job 978** (`Consumer CPOR Tracking Table 20260813.xlsx`): 1191 cases staged; **305 applied / 879 blocked**; **0 duplicate `case_code`s**. Native cases untouched
- Takealot covering **2026-08-13:** `C26759823` (id 310, 23 lines) and `C26760971` (id 311, 18 lines). Steward: FA608PM → product **4959** (listing 71); FA608UH/G615LM skipped (ambiguous sales-model twins); duplicate grains last-wins after skip extras
- BACKLOG-130 **proven today:** Takealot poll 24/24. Activation prefers **Sell-Through line window**; **Sell out PP** only when no covering promo. FNB Day 9999 no longer applies on 13 Aug (listing 64 → sell-out 14999 `price_consistent`). Listing 65 still `not_activated` vs promo 7999 (10–16 Aug).

## Locks 2026-08-13

- 094 MAC = SOH + in-window intake, weighted; units = history benchmark; all planner fields editable
- Target cover = **weeks per customer**
- No forecast file — CIP computes from history
- Generic lineup export OK if required column layout via profile
- 092 owed (interim) = approved `ttl_support`; paid = mapped evidence; never invent owed from qty×support

## Next

1. **New chat:** Unit 13 — `feat/unit13-cpor-payment-recon` off `main` after P5 merge (or off this branch if P5 waits)
2. Warren: merge/promote `feat/p5-residual` when ready
3. Do not re-ingest job 978 / do not re-audit Takealot REST fetch
4. Skip (already in tree): Unit 8; BACKLOG-026/027/044/045; P6 Settings light (096 + export sheet titles). Full P6 still waits for a second company. REST + activation live on this branch, not yet `main`.

**Env:** local Windows. Web `:3000` + API `:8001` restarted 2026-08-13 for smoke.
