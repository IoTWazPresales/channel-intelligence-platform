# Spec — CPOR Promotion Funding v1 (Reseller Channel) + Listing Capture v0

**Date:** 2026-07-08
**Status:** Draft for Warren review
**Evidence base:** `Consumer_CPOR_Tracking_Table_20260623.xlsx` (all 4 sheets decoded, math verified row-level); substrate audit 2026-07-08 (Grok, read-only, verified `current_database() = cip`); `docs/PROMOTION_PLANNING_DATA_SUBSTRATE_AUDIT.md` (2026-06-14 baseline).
**Prerequisite:** commit the 2026-07-08 substrate audit report to `docs/` before implementation begins.

---

## 1. Scope

**In scope (v1):**
- CPOR case + line model at the workbook's native grain (reseller channel).
- Pricing waterfall engine (configured steps, tenant-scalable).
- Customer commercial terms (default margin/rebate) via `commercial_customer_term` pattern.
- Cost-basis suggestion from DSI sell-out evidence + manual override with provenance.
- Proposal artifact: workbook export in the current Reseller-sheet layout + per-case USD pivot summary; PM approval workflow (reuse promo_export state machine pattern).
- Settlement: case-scoped claim-evidence import (product × date × units) → Result → payable support → consolidation view.
- Deprecation/migration of the dead promo scaffold consumers.

**Out of scope (v1) — each gets a BACKLOG entry (§9):**
- Disti channel (Disti Sell out sheet = price directive to distributor) incl. rebate + disti-margin waterfall steps and DSI SOH cost ingestion.
- New-DAP price protection (re-invoicing incoming stock at target DAP) — lives in the disti channel.
- Budget reservation/consumption ledger (computed budget requirement only in v1).
- FX rate table (case-level ROE snapshot, manual entry, in v1).
- Customer approval link / portal.
- ASUS-side product cost / profit analytics.
- Elasticity / uplift measurement.
- Listing intelligence (promo-activation detection) — Listing Capture v0 collects only.

---

## 2. Domain model (verified from workbook)

### 2.1 Pricing waterfall — reseller channel
```
dealer_price   = SRP / (1 + vat_rate) * (1 - dealer_margin_pct)
support_unit   = max(0, cost_basis - dealer_price)        -- clamp: float-epsilon rows in source
ttl_support    = support_unit * estimate_qty              -- proposal / budget ask
ttl_result     = support_unit * result_qty                -- settlement; NOT capped by estimate
support_usd    = support_unit / case_roe                  -- PM budget number
```
Verified: SRP 13,999 / 1.15 × 0.85 = 10,347.09; support 9,585.07 − 9,334.11 = 250.96; result 49 × 250.96 = 12,297.18 (uncapped above estimate 20). Reseller sheet omits rebate and disti-margin steps (those are disti-channel).

**Engine design:** waterfall = ordered list of configured steps per channel (`vat_divide`, `margin_deduct`, `rebate_deduct`, `disti_margin_deduct`). Channel config selects steps. Adding the disti channel later = config + one cost-source, zero engine rework. Tenant conventions are config, never constants.

### 2.2 Grain
- **Case** = one customer × one promo window × one promotion type (e.g. "Evetech Jan Sell Out Support"). External case code preserved (`C23C17803` style) for legacy; new cases get generated codes.
- **Line** = case × product × distributor(source of stock) × optional POD-quarter layer. Workbook shows the same model split across intake layers with distinct SOH/cost/estimate/result — layers are explicit rows, never system-fabricated depletion. **No FIFO fabrication** (settled principle).
- Estimate is a target, never a cap. Optional per-line `cap_qty` (nullable) for the rare budget-constrained case (Warren: caps only under extreme budget pressure).

### 2.3 Case lifecycle
```
draft → proposed → approved | rejected → active → ended → settled | cancelled
```
- `cancelled` retained with zero payable (workbook precedent: JD Furniture C23C16018).
- Reuse promo_export approval mechanics: resend-after-reject = new version, event trail, actor header. Rejected cases carry PM feedback comment.
- Soft everything: cases and lines never hard-deleted; supersession pointer if re-issued.

### 2.4 Promotion type
Config vocabulary (`Sell out PP`, `Sell-Through PP`, `Stock PP (In-Direct)` seeded from workbook; steward-extendable). Also note `PT` product line appears in a source pivot — BU vocabulary is already tenant config; ingest as-is, flag unknown BUs, never block.

---

## 3. Data model (new tables; names indicative)

| Table | Grain | Key fields |
|---|---|---|
| `cpor_case` | case | case_code (unique), customer_id, promotion_type, window_start, window_end, status, roe_snapshot, currency_code (default ZAR), channel (`reseller` only in v1), notes, created_by, approval fields/version |
| `cpor_case_line` | case × product × distributor × layer | product_id, distributor_id (nullable), pod_quarter (nullable layer tag), srp, vat_rate, dealer_margin_pct, margin_source (`customer_default` \| `manual_override`), cost_basis, cost_source (`sellout_evidence` \| `manual`), cost_evidence_json (rows/date-range used), estimate_qty, cap_qty (nullable), soh_snapshot (nullable), computed: dealer_price, support_unit, ttl_support, support_usd; result_qty (settlement-written), ttl_result, remark |
| `cpor_case_event` | event | case_id, event_type, actor, payload_json — approval + status + override audit trail |
| `cpor_claim_evidence_line` | claim import line | case_id, import_job_id, product_id (resolved), source_model_token, sale_date, units, unit_price (optional), raw_source_row JSONB, source_key |
| `commercial_customer_term` (extend existing) | customer × term | ensure margin_pct + rebate_pct usable as CPOR defaults; steward CRUD surface |

Rules carried over from platform principles:
- `source_key` upsert on claim evidence; raw_source_row always preserved.
- Product resolution on claim lines uses the standard tier order (item → EAN → sales model); unresolved = flag + worklist row, **never** auto-create, never blocks the rest of the claim.
- New writers → migrate all readers (§7).
- Computed columns recomputed server-side on any input change; never trust client math.

---

## 4. Cost-basis suggestion service

Preference order (each with provenance in `cost_evidence_json`, deviation flags between tiers):
1. **Customer-reported cost** from CST feed (Takealot Weighted Avg Cost Price, Dispo MAC, Computer Mania COST — confirmed present in real feeds 2026-07-08) — latest report ≤ case creation.
2. **DSI sell-out evidence**: `fact_sales_sellout.unit_sellout_price_ex_tax_amount` (35,582/35,583 populated on cip) — weighted average per (customer, product) over configurable lookback (default: since last CPOR case for that product, else 180 days), per-quarter layered breakdown available for line-splitting.
3. **Manual** (workbook remark "Cost price updated as per Pinnacle" proves the workflow) — `cost_source='manual'`.

**MAC staleness (Warren 2026-07-08):** reported MAC is a snapshot; pre-promo stock intake at a different price changes the correct funding basis. All signals surface with as-of dates; on case transition to approved/active the suggestion recomputes and any movement flags `cost_basis_drift` (old vs new). Flag only — never auto-rewrite an approved number; KAM/PM decides.
- `currency_code` on sell-out is 0-filled → tenant config `assumed_sellout_currency = ZAR`, flagged assumption, surfaced in cost_evidence_json.
- Manual override always available (workbook remark "Cost price updated as per Pinnacle" is a real workflow); `cost_source='manual'` + deviation-from-evidence flag. FLAG ≠ BLOCK.
- No sell-out evidence for (customer, product) → line requires manual cost, flagged `no_cost_evidence`.

---

## 5. Proposal & approval

- **PM proposal view** = the workbook pivot: per case, POD Quarter × Product Line → Ttl Support USD (and later Result USD). USD via case `roe_snapshot` (manual entry v1; no FX table exists — confirmed).
- **Export artifact**: XLSX in the current Reseller-sheet column layout (presentation contract — customers copy/paste into their own upload docs) + pivot summary sheet. Generated from case lines; versioned like promo_export.
- **Approval workflow**: draft → pending_approval → approved|rejected, PM feedback on reject, resend = new version. Reuse existing pattern (endpoints/events per 2026-07-08 audit item 7).

---

## 6. Settlement

- **Input**: customer's CPOR sales submission — per product, per date, units (the artifact customers already send). New import type `cpor_claim_evidence`, case-scoped (steward selects target case at upload).
- Attribution: `sale_date` within case window → counts toward `result_qty`; out-of-window rows retained + flagged `out_of_window`, excluded from payable (steward can include with override + reason).
- **Consolidation view** (case end): per line — estimate vs result, support_unit, ttl_result ZAR/USD, flags (over-estimate, out-of-window included, unresolved products). Output: settlement summary artifact for finance. Case → `settled` on steward confirmation.
- **CST relationship (resolved 2026-07-08 from 10-file corpus):** no customer feed carries daily rows — CST stays week/month grain, so **claim-evidence import is the settlement source of record** (customers send daily POE files regardless). CST (U4.5) is the reconciliation layer: where CST rows exist for a settled case's customer/window, claimed-vs-CST divergence flags — flag, never block.

---

## 7. Promo scaffold deprecation (new writer → migrate ALL readers)

Consumers of `fact_promotion_plan` / `dim_promotion` (all tables 0 rows on cip — no data migration, readers only):

| Consumer | Action |
|---|---|
| CPOR XLSX export service (`promo_export/cpor_xlsx.py`) | Re-point to `cpor_case`/`cpor_case_line`; new column layout per §5 |
| Promotions UI/API (`/promotions`, plans/readiness tabs) | Replace with CPOR case UI; readiness tab decision at implementation discovery (likely park) |
| `product_rankings.py` (intelligence) | Reads promo signals — re-point or explicitly no-op with comment; must not silently read empty deprecated tables |
| `product_usage.py` delete-impact | Add `cpor_case_line` reference check; keep old checks until tables dropped |
| Seed scripts | Stop seeding deprecated tables |
| `template_definitions.py` `promotion_plan` (stub_noop) | Remove/replace with `cpor_claim_evidence` template |
| DSI `_has_cpor_data()` (always False) | Wire to real CPOR data or remove |

Old tables: keep (empty) through v1; drop is a separate later migration decision.

---

## 8. Listing Capture v0 (parallel thin track — capture only)

Rationale: price/availability history accrues value with calendar time; the intelligence layer (promo-activation detection) depends on CPOR cases existing, so it waits — capture does not.

- `customer_listing` registry: customer_id, product_id, url, marketplace (config vocab: takealot, evetech, …), status lifecycle `active | out_of_stock | delisted | dead_link` (observed, never deleted — delisting history is intelligence), registered_by/at. Seed: manual entry + CSV import + **feed-derived proposals** (Takealot Product ID/TSIN and Evetech Web ID arrive in CST feeds per U4.5 — auto-propose, steward confirms); feeds later.
- `listing_observation`: listing_id, fetched_at, http_status, raw_snapshot (compressed HTML/JSON), parser_version, extracted: price, availability, promo_badge (nullable), parse_status. Parse failure = flag + retained snapshot, never blocks; re-parse without re-fetch when parsers improve.
- Scheduler: Celery beat, per-marketplace polite rate limits, dead-link cadence backoff.
- **Non-goals v0:** SEO/listing-content auditing, competitor discovery, auto URL discovery, promo-activation alerts (v1 of intelligence, post-CPOR), any customer-facing surface.

Hard dependency ordering: **CPOR v1 units first**; Listing Capture v0 is one small self-contained unit that may interleave but never displaces a CPOR unit mid-flight.

---

## 9. BACKLOG entries to write at spec acceptance

1. **Disti channel + New-DAP price protection** — waterfall steps (rebate, disti margin), DSI SOH cost ingestion (cost column not captured today — parser + schema), New-DAP re-invoice mechanism. Trigger: business needs disti price-directive cases in-platform.
2. **Customer approval link/portal** for settlement sign-off. Trigger: first case reaches `settled` via manual flow.
3. **ASUS-side product cost / profit definition** (PM controlled cost vs DAP vs landed) — for lineup planning profitability + CPOR margin analytics. Trigger: lineup profitability work or first request for CPOR ROI beyond support totals. (Warren flagged 2026-07-08.)
4. **FX rate table / ROE governance** — replace manual case ROE. Trigger: multi-case ROE inconsistency observed or hedged/booked rate requirement.
5. ~~CST ↔ claim reconciliation~~ — **pulled into scope**: BACKLOG-013 un-parked as U4.5; reconciliation ships in U5. Mark BACKLOG-013 resolved when U4.5 lands.
6. **Listing intelligence v1** — promo-activation detection (active CPOR case + observed price > funded price past window start → worklist), price-drift alerts. Trigger: CPOR v1 live + ≥2 weeks of observations on relevant listings.
7. **Budget ledger** (reservation → consumption → reconciliation) — unchanged from Jun-14 audit gap list. Trigger: PM budget process formalized (the "50/50" policy question).
8. **Price elasticity / "what price it would move at"** — requires promo-response history that CPOR settlements generate. Trigger: ~5–10 settled cases with claim evidence across ≥3 customers. Building sooner fabricates confidence from absent data.
9. **Competitor listing monitoring** — extend `customer_listing` registry with competitor/marketplace listings for the same products; price-position intelligence. Trigger: LC v0 stable + first competitive-pricing decision explicitly needed.

---

## 10. Implementation sequencing (each = one Cursor prompt, one surface)

1. **U1 — Models + terms:** cpor_case/line/event + claim-evidence tables, migration, `commercial_customer_term` extension + steward CRUD. Model + migration committed together.
2. **U2 — Waterfall + cost service:** engine (configured steps), cost-suggestion service, computed-field recompute path, unit tests against workbook-verified numbers (the row-level examples in §2.1 become fixtures).
3. **U3 — Case UI:** case builder (create → lines with defaults pull-through, cost suggestions, overrides, layer split), lifecycle actions, approval flow, USD pivot view.
4. **U4 — Export:** XLSX artifact (Reseller layout + pivot), versioning, approval integration.
4.5. **U4.5 — CST D1 surface (un-parks BACKLOG-013; corpus of 10 real files analyzed 2026-07-08; canonical shape confirmed by Warren 2026-07-08):**
   - **Grain confirmed week/month — no daily extension.** No customer file carries daily sales rows; existing `fact_customer_sellthrough` grain survives unchanged. Settlement remains claim-evidence-primary (customers must send daily POE files regardless); CST becomes the reconciliation layer.
   - **Canonical staging columns (Warren-specified):** product tokens (ASUS SKU / EAN-UPC and/or Sales Model — standard tier resolution), period (steward-declared), units_sold, soh_qty, unit_sell_price (+ `vat_basis` per profile, default `ex_vat`), **site_label (first-class, nullable — MUST exist in the model even for siteless reports; per-store intelligence depends on it)**, unit_cost **and** unit_mac (separate fields — Takealot reports both). Optional distributor/supplier attribution retained in staging. Raw_source_row always.
   - **Site → location:** facts carry `site_label` verbatim; new labels per customer feed a steward-confirmed location worklist mapping to `customer_location_id` (exists on CST fact per Jun-14 audit — verify at discovery). No auto-create of locations; unmapped labels never block apply.
   - **Period = steward-declared at upload, file-corroborated** (reuse lineup layered-detection pattern): steward selects reporting week (some files cannot self-describe range); filename/banner/pivot-column signals corroborate; conflicts surface to steward, never silently picked. Week convention Mon–Sun as tenant config; per-case override allowed (cases usually but not always Mon–Sun).
   - **Expected-report tracker:** key-account flag on customer master with cadence → per-week slots: due Monday (for prior Mon–Sun week), `late` Tuesday, `missing` worklist + notification thereafter.
   - **Per-customer feed profiles** (declarative config, steward-editable — variance lives here, never in the canonical model): sheet roles (sales/SOH/combined; sheet-per-week workbooks → target-sheet selection), header strategy (multi-row BEx headers, banner rows, ragged columns), period-signal sources, column semantic map, brand/vendor row filter (Amazon carries non-ASUS rows), vat_basis.
   - **New resolution tier: `customer_article_alias`** (customer × retailer article no. → product). Learned where article + model/EAN co-occur (Dispo), applied where only article exists (Game BEx). Exact-key alias table, flag-not-block, no description fuzzy-matching (no-weak-joins). Cross-file alias learning is steward-confirmable, never silent.
   - **Listing seed side-channel:** Takealot Product ID/TSIN and Evetech Web ID captured from feeds → auto-propose `customer_listing` registry entries for LC-U1 (steward confirms).
   - Evidence corpus (retain as parser fixtures): Takealot ASUS_WEEK_27; Game/Makro SAP BEx Asus_Sales_W27; Massmart Dispo.XLSX; JD ASR Asus_ASR; Computer_Mania_week_27; Evetech Sales+Inventory pair; Amazon Vendor Central Sales_ASIN+Inventory_ASIN pair; monthly-pivot small dealer Asus_sales_and_SOH_2025.
4.6. **U4.6 — Channel intelligence read-model v1 (small unit):** per (customer, product [, site]): trailing velocity, weeks-of-cover (soh ÷ velocity), aged/dead-stock flag (SOH > 0, velocity ≈ 0 over N weeks at current sell price = "not selling at the given price"), velocity trend. Read-only over U4.5 facts; explainable factors, no black-box scoring. Elasticity ("what price it would move at") and competitor pricing are explicitly NOT in this unit — see BACKLOG §9.
5. **U5 — Settlement:** claim-evidence import (template, parser, staging → apply with source_key) as source of record; CST reconciliation flags; consolidation view, settle action.
6. **U6 — Scaffold reader migration** (§7 table) + nav.
7. **LC-U1 — Listing Capture v0** (whole of §8, one unit).

Standard constraints on every prompt: no imports/writes against cip without explicit approval; clone-proof any destructive path; discovery-quote-before-change; done-state checklist; CONTEXT.md addition with every commit.

---

## 11. Open items (non-blocking, resolve during U1 discovery)

- Exact `commercial_customer_term` shape (audit: margin + rebate exist, 1 row) — extend vs new table decided from code inspection.
- Whether `distributor_id` on lines is mandatory (workbook always names one) or nullable for direct-fulfilment edge cases — Warren call at U3.
- Readiness tab fate (park vs delete) — U6 discovery.
