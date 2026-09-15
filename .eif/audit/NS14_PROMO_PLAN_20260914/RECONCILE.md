# N-0026 reconcile — propose a promotion plan from customer + period

Run: `NS14_PROMO_PLAN_20260914`. Actor: `gov-001`.
Architecture cited: **D-0008** (accepted commercial amendment of N-0013) — Promotion Planner authors `cpor_case` / `cpor_case_line`; CIP-proposed plans draw on historical comparables, stock/cover, lineup, customer terms, listing/market evidence.
Settled: competition = **product** competition (our SKU vs competing SKUs). Customer-versus-customer comparison is out of bounds.

`current_database()=cip` printed first. Queries read-only. 2026-09-14.

## B4 draft path today (VERIFIED from source)

| Step | Where | Stops |
|---|---|---|
| Compose | `GET /api/v1/cpor/intelligence/promo-plan-draft?seed_case_id=` → `build_promo_plan_draft` | `seed_case_id` is required (`Query(..., ge=1)`). Lines come only from that case’s `cpor_case_line` (or client `lines[]` on recompute). |
| Comparables | `build_comparable_cases(session, case_id=seed_case_id)` | Requires a seed case. Ranks **other cases including other customers** (same-customer is only the highest axis). |
| MAC | `suggest_intake_weighted_mac` per line | Wired. Needs customer_id + product_id + window (from seed). |
| Forecast | `fact_demand_forecast` 13-week sum | Wired. Fallback: mean of comparable estimate_qty, then seed line qty. |
| Cover target | `resolve_target_cover_weeks_sync` | `commercial_customer_term.target_cover_weeks` else tenant default. Does **not** read `weeks_of_cover_observation`. |
| Budget check | `derive_planned_reservation_sync` from `fact_lineup_plan_item` (SRP from lineup lines) vs Σ `cpor_case_line.ttl_support_usd` | Optional; used when `planned_support_usd` omitted. |
| Create | `POST .../promo-plan-draft/create-case` | Raises `seed_case_not_found` if the seed id is missing. Copies seed customer, window, promotion_type, tenant. Status `draft`. **Does not set `origin=proposed_by_cip`** (defaults `native`). |
| UI | `PromoPlanBuilderPanel` behind “Propose a plan” | Hand-typed seed case id + period. No customer picker. |

Manual empty create already exists: `CreateCaseDialog` → `POST /cpor/cases` (customer + window, no lines). That is not a proposal.

## Evidence sources (code vs live cip)

| Source | In compose today | Live `cip` | Trust | Node action |
|---|---|---|---|---|
| Historical same-customer cases + line pricing (`cpor_case` / `cpor_case_line`) | Only as seed lines or as A2-05 ranked comparables (includes other customers) | 311 cases (211 settled, 74 ended, 23 cancelled, 3 draft); 658 lines; 44 customers; origin 306 historical_import / 5 native | Trustworthy book | **Use** same-customer history as fallback product set and same-customer comparables only |
| Cross-customer analogue ranking | Wired in A2-05 | Same table | Out of bounds for proposal | **UNCOVERED** — do not use other customers’ cases to propose this customer’s plan |
| Current cover / SOH | MAC bucket A on-hand (display + blend); target weeks from terms | `weeks_of_cover_observation` 194349 rows; terms 11 rows, **0** `target_cover_weeks` | Observed cover exists; **target** cover from terms is empty (tenant default) | Keep existing MAC + term resolver. Do **not** substitute observed WoC as target cover (different grain). Record UNCOVERED for observed-cover-as-proposal-input |
| Lineup evidence | Reservation derive from `fact_lineup_plan_item` (all 1647 rows are period **2026Q2**, 604 customers). Line identities not used as the proposed SKU set | `commercial_lineup_line` 2447 rows with product+customer (19 customers, 411 products). Customer 18 × 2026Q2: **46 lines / 40 products, all with SRP** | Lineup **cases** have mixed periods; `fact_lineup_plan_item` is Q2-only | **Use** active `commercial_lineup_line` for that customer + period as the primary product set. Reservation derive stays Q2-only when that is the period |
| Customer terms | Cover weeks + default margin on create | 11 terms; cover weeks all null | Partial | Wired; null cover → tenant default (already). Do not invent terms |
| Listing evidence | Not joined on lines (Related / Market only) | `customer_listing` 218 rows, **3** customers (52, 20, 299); `listing_observation` 168 | Sparse; not the proposing customer set in general | **UNCOVERED** — do not substitute a 3-customer listing panel as a plan seed |
| Competitor prices | Not joined | `fact_competitor_price` **0** rows | Empty | **UNCOVERED** — no weaker substitute |
| Forecast | Wired | 38625 rows, 2026-06-19…2026-09-11, 667 customers, 362 products | Trustworthy in window | **Use** |
| Claim evidence / uplift | Headline dash | `cpor_claim_evidence_line` **0**; ended-with-claims **0** | Cannot derive uplift | **UNCOVERED** — keep “not derived” |

## What “seed case id” requires vs customer + period

Seed case id today is a **proxy** for: customer, window, promotion type, tenant, and the SKU/distributor/SRP/qty identities on its lines.

Customer + period instead needs: `customer_id`, parseable `period_label` → quarter window, product identities from **lineup for that customer and period** (primary) or **that customer’s historical lines** (fallback), promotion type (operator pick or default existing vocab), tenant from the user/customer. No second economics ledger.

## Headline strip (VERIFIED)

Five figures: In planning (draft+proposed+approved+rejected = **3** drafts), Live now (**0** active), Awaiting review (**0** proposed), Budget reservation used **257%**, Uplift **—**.

257% is `support_bias` totals actual_usd **773096.05** / planned_usd **300818.87** on **same case lines that have SKU assumptions** — not lineup-derived, despite the caption. NUMBER RULE: do not show that ratio. Show the two USD amounts with the true grain, or drop the ratio.

Planner-actionable live grains: drafts **3**, ended **74**, settled **211**, SKU-economics planned reserve and actual support as separate figures.

## Start work

No verb opens Promotion Planner. `?new=1` opens empty create. This node adds **Create promotion plan** → `/promotions?propose=1` (propose workbench), planner + admin.

## Out of this node (BACKLOG / later)

Listing join onto lines; competitor ingest; observed WoC as proposal input; uplift; A2-05 cross-customer ranking change (keep for the seed-case intelligence view unless called from propose); N-0025 limitations; D-0002.
