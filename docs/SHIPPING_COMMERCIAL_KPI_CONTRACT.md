# Shipping commercial KPI contract

**Status:** authoritative for `/shipping` commercial-summary cards and matching smart presets.  
**Source:** Phase 0 cip diagnostic 2026-07-27 (`apps/api/.tmp/shipping_kpi_phase0_diag.json`); plan “Shipping commercial KPI + filter contract rebuild”.

Code is evidence — if this doc and `shipping_commercial_summary` / `shipping_commercial_kpis.py` disagree, stop and ask Warren.

---

## Shared vocabulary

| Term | Definition |
|------|------------|
| **Effective arrival date** | `coalesce(eta_date, promise_date)` on `fact_inbound_shipment` |
| **Not landed** | `pod_date IS NULL` |
| **Scheduled (open cargo)** | `status = 'scheduled'` |
| **Current-incoming window** | Effective arrival date ∈ `[reference_date, reference_date + 90 days]` inclusive |
| **Stale promise cutoff** | `promise_date < reference_date − 180 days` → **stale** (not Overdue KPI) |
| **Reference date** | UTC calendar date used by the API (`reference_date` in the payload) |
| **ISO week** | Monday–Sunday containing `reference_date` (`week_start` / `week_end`) |
| **Grain** | What the hero number counts: **value** (money), **qty** (units), or **lines** (fact rows) |

Fact grain is always one `fact_inbound_shipment` row. Cards must never label money as units or lines as products.

---

## Default cohort (unfiltered page)

When no user filters are active, every commercial KPI below is computed against its **own contracted predicate** (not “all fact history”).

When any filter is active (fact filters **or** lineup chips **or** `cohort=` smart preset), each KPI = **contracted predicate ∩ active filter set**. Cards and `/lines` share one filter contract.

---

## Filter inheritance

`GET /commercial-summary`, `GET /eta-shifts`, and `GET /lines` accept the same query params:

Fact: `import_job_id`, `distributor_id`, `customer_id`, `purchase_order_id`, `line_state`, `report_type`, resolution statuses, `status`, `search`, `eta_from`/`eta_to`, `date_field`/`date_from`/`date_to`, `pod_date_is_null`, `currency_code`, `operating_unit`, `product_family`, `product_model`.

Lineup (same enrichment path as `/lines`): `plan_quarter`, `plan_quarter_label`, `plan_business_unit`, `lineup_attribution`, `lifecycle_bucket`, `slip_direction`.

Cohort shortcut (smart presets / card click): `cohort` ∈  
`current_incoming` | `overdue` | `arriving_week` | `landed_week` | omitted.

`date_field=effective_arrival_date` filters on `coalesce(eta_date, promise_date)`.

---

## KPI dictionary

### 1. Pipeline value (current incoming)

| Field | Contract |
|-------|----------|
| **Hero** | Lead currency **value** (`sum(amount)` where amount not null), by `currency_code` |
| **Secondary** | Total **qty** (`sum(quantity)`), **line_count** |
| **Predicate** | `status='scheduled'` AND `pod_date IS NULL` AND effective arrival ∈ current-incoming window |
| **Not** | Sum of all historical `scheduled` amounts |
| **cohort=** | `current_incoming` |

### 2. Arriving this week

| Field | Contract |
|-------|----------|
| **Hero** | **qty** (`sum(quantity)`) for the cohort |
| **Secondary** | **line_count**; distributor breakdown by **qty** (and line count) |
| **Predicate** | `status='scheduled'` AND `pod_date IS NULL` AND `eta_date` ∈ ISO week |
| **cohort=** | `arriving_week` |

### 3. Delivered this week

| Field | Contract |
|-------|----------|
| **Hero** | **line_count** (POD grain matches operator “landed lines”) |
| **Secondary** | **qty** |
| **Predicate** | `status='received'` AND `pod_date` ∈ ISO week |
| **cohort=** | `landed_week` |

### 4. Overdue

| Field | Contract |
|-------|----------|
| **Hero** | **line_count** |
| **Secondary** | **qty**; pct of current-incoming pipeline line_count |
| **Predicate** | `status='scheduled'` AND `pod_date IS NULL` AND `promise_date` not null AND `promise_date < reference_date` AND `promise_date >= reference_date − 180` AND effective arrival ∈ current-incoming window (requires a future/current **eta** when promise is already past) |
| **Stale (excluded)** | Same but `promise_date < reference_date − 180` — reported only as `stale_promise_line_count`, not in Overdue hero |
| **cohort=** | `overdue` |

### 5. ETA shifts

| Field | Contract |
|-------|----------|
| **Hero** | Counts of observation pairs where effective date (obs `coalesce(est_pod, promise)`) moved later (**slipped**) or earlier (**improved**) |
| **Scope** | Only facts in **current-incoming** (∩ active filters). Not lifetime LAG over all evidence |
| **Method** | LAG over `shipment_evidence_observation` by `line_identity_key` ordered by `valid_from`; join to scoped facts via `shipment_evidence_line_id` |

---

## Response shape (commercial-summary)

Each money/qty KPI exposes at least:

```json
{
  "value_by_currency": [{"currency_code": "USD", "amount": 0}],
  "quantity": 0,
  "line_count": 0,
  "cohort_definition": "current_incoming",
  "filter_scope": {"active": false, "cohort_line_count": 0}
}
```

Top-level also returns `cohort_definitions` (human strings), `reference_date`, `week_start`, `week_end`, and `stale_promise_line_count`.

---

## Explicitly out of scope

- Changing fact `amount` / import amount semantics from the shipping UI  
- Open→shipped double-count remediation (BACKLOG-062)  
- Full `MasterDataGridShell` migration of `/shipping`  
- Plan vs Executed fill-rate math  

---

## Phase 0 snapshot (cip · 2026-07-27)

| Metric | All scheduled (old card) | Current-incoming gate |
|--------|--------------------------|------------------------|
| USD pipeline value | **$288,189,046** (1,797 lines w/ amount) | **$63,439,107** (1,341 lines) |
| Amount with **no** effective date | **$213,948,685** (267 lines) | excluded |
| Overdue lines | 1,049 | 884 (contracted) |
| ETA slipped | 841 lifetime-scoped | 810 current-incoming |
| Arriving this week | 57 lines | **6,653 units** / 57 lines |

Top contributors to the $288M were open_order rows with null ETA/promise and ~$36M amount on qty 36 (unit-price scale corruption) — parked as data-quality BACKLOG, not fixed by KPI rewrite.
