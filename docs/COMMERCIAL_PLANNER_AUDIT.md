# Commercial Planner Audit

**Date:** 2026-05-17
**Branch:** `cursor/customer-sales-pipeline-2787`
**Scope:** Full audit of the commercial planner module — frontend page, API endpoints, feature components, and cross-module integration with exceptions and dashboard.

---

## 1. Current State

### 1.1 What Works

| Area | Status | Evidence |
|------|--------|----------|
| **Plan CRUD** | Working | Create, list, patch, delete plans via API. Frontend renders plan selector, create dialog, and inline edit for plan metadata. |
| **Plan line CRUD** | Working | Add single lines via entity search (customer + distributor + product), inline-edit target units/SRP/promo in AG Grid, delete lines. API validates and persists. |
| **Add product set (batch)** | Working | 4-step stepper dialog: select customer/distributor, pick products via ProductPickerDialog (multi-select with checkboxes), preview with per-row unit/SRP overrides, duplicate detection against existing plan lines, sequential API creation. |
| **Planner defaults maintenance** | Working | Full CRUD for customer terms (margin + rebate), distributor terms (margin), and SKU assumptions (controlled cost amount + currency, VAT, FX bridge, reserve total, promo reserve split). Inline edit dialogs with entity search. |
| **SKU economics bulk import** | Working | CSV template download, file upload → preview (match by SKU, part_number, sales_model+model_name), blocking-error gating, confirm checkbox, apply with create/update summary. API endpoints: `import-template`, `import-preview`, `import-apply`. |
| **Economics calculator** | Working | `compute_line_economics()` in `calculator.py`: weighted SRP, VAT strip, margin stack, FX bridge, reserve allocation, internal GP. Persists `calc_*` fields on plan lines. Recalculate endpoint rebuilds all lines in a plan. |
| **Economics trust tiers** | Working | Three-tier system (ok / warning / blocked) derived from `calc_flags`. Blocking flags: missing controlled cost, invalid FX, impossible economics, non-positive inputs. Warning flags: missing terms, partial margins, UNASSIGNED distributor, placeholder economics. |
| **Field provenance (read model)** | Working | `plan_line_read_model_extensions()` returns `economics_field_provenance` dict keyed by field name with `{source, trusted, detail}`. Sources: `line_override`, `planner_default_terms`, `sku_economics_input`, `placeholder_or_missing`. |
| **Line economics waterfall** | Working | `LineEconomicsWaterfall` component renders sections A (customer-facing stack), B (economics outputs), C (internal cost/GP), D (evidence). Provenance chips per field. Trust alert banner. Currency legend. |
| **Plan readiness** | Working | API `compute_plan_readiness_payload()` checks system reference dims (OPEN_CHANNEL, UNASSIGNED), missing terms/SKU assumptions, invalid controlled cost/FX/VAT/reserves, UNASSIGNED distributor usage, calc_flags. Frontend renders readiness banner. |
| **Recalculate with trust summary** | Working | POST `.../recalculate` returns `recalculate_trust_summary` (counts by tier + top blocker flags) and `economics_plan_trust`. Frontend displays post-recalculate banner. |
| **Column selector** | Working | `ColumnSelectorModal` with grouped toggles: identity (locked), product spec, catalogue, planning inputs, SKU economics, plan-currency bridge, economics outputs, issues. View presets (planning, product_spec, commercial, economics). Discovered spec JSON keys from server metadata. LocalStorage persistence with version migration. |
| **Suggestions engine** | Working | `build_quantity_suggestion`, `build_pricing_suggestion`, `build_promo_mix_suggestion` with multi-source inputs (sellout, prior planned, forecast, lineup evidence). Preview dialog showing before/after values. Apply flow patches the plan line. |
| **Current lineup section** | Working | Lineup case CRUD (upload CSV, list cases, workbench view). Dynamic workbench columns: raw upload columns, parsed fields, catalogue product fields, catalogue spec keys, sync fields. Entity resolution dialog (map to existing customer/distributor, mark as open channel staging, redirect customer token as distributor). Sync-to-plan flow. |
| **Commercial data map** | Working | `CommercialDataMap` component: read-only reference table of 20+ commercial concepts with DB field, user-facing label, type (input/evidence/output/override/system), edit/display locations, readiness impact, calculator impact, currency notes, and risk notes. |
| **Exceptions page** | Working | AG Grid list of exception rows with type, severity, title, status, "Why" chip → drawer. Delete individual + clear-all with confirmation. Empty state guides to data imports. |
| **Dashboard** | Working | KPI cards (open exceptions, budget requests in flight, inbound shipments tracked), stock health snapshot (JSON pre-formatted), recommended actions list. "Getting started" link. |

### 1.2 What Is Partial

| Area | Status | Details |
|------|--------|---------|
| **Line overrides UI** | Partial | `override_controlled_cost_amount` is exposed and editable on plan lines. Override fields for margins, VAT, FX, reserves are stored in DB and respected by the calculator, but the frontend grid does not expose inline editors for all override fields (only controlled cost override shows in the line detail). |
| **Plan-currency bridge columns** | Partial | `calc_sell_in_price_local` and `calc_distributor_net_local` are defined as optional grid columns but their computation (reverse FX bridge from economics output back to plan currency) depends on correct FX being set. The API read model computes these via `plan_line_read_model_extensions`, but if FX is placeholder, values are misleading. |
| **Historical lineup coverage** | Partial | Lineup coverage endpoint exists and renders product gaps, evidence fields, and DAP semantics. However, the lineup-to-plan sync currently only handles single-case sync — multi-case merge or period-over-period comparison is not built. |
| **Suggestions data sources** | Partial | The suggestion engine queries `FactSalesSellout`, `FactForecast`, `FactPricing`, and `HistoricalLineupImportLine` for inputs. If fact tables are missing or empty, suggestions degrade to "low confidence" fallbacks. The `_meta.data_sources` flags are returned but not prominently surfaced in the UI. |
| **Export / publish flow** | Partial | Plan statuses include `draft`, `review`, `approved`, `published` but no export-to-file or publish-to-downstream-system is implemented. Status transitions are simple string updates without workflow validation. |
| **Dashboard stock health** | Partial | Renders `stock_health` as raw JSON (`JSON.stringify` in a `<pre>` tag). No visualization or structured display. |
| **Plan metadata editing** | Partial | Country code and currency code can be set on plan create and patched, but the plan header UI does not expose a dedicated country/environment picker. The environment field exists on the `Plan` type but is not surfaced in the create or edit dialogs. |

### 1.3 What Is Missing / Planned

| Area | Status | Details |
|------|--------|---------|
| **FX provider automation** | Missing | SKU FX is manually entered and locked. No provider integration, accept/lock step, or scenario table. Explicitly deferred per `CommercialDataMap` and SKU dialog disclaimer. |
| **True landed cost** | Missing | Controlled cost = PM bottom only. Logistics, duties, freight, insurance, handling are not modeled. Explicitly deferred with UI disclaimers. |
| **Payment terms / distributor rebate** | Missing | Listed as deferred in `CommercialDataMap`. No DB columns or API fields. |
| **Pricing simulation** | Missing | Economics outputs are per-line, one-shot recalculate. No what-if simulation, scenario comparison, or batch pricing optimization. |
| **BOM/configurator integration** | Missing | No simulated controlled cost from bill-of-materials or product configurator. |
| **SOH (Stock-on-Hand) calculation** | Missing | Referenced in the task scope but not present in commercial planner. Would need separate inventory/SOH module integration. |
| **Customer sales pipeline** | In progress | Migration `20260517_0038_customer_sales_retail_promotion_tables.py` exists. Models in `customer_sales.py`. Not yet integrated with commercial planner. |
| **Approval workflow** | Missing | Plan statuses are flat strings without state machine, role-based transitions, or audit trail of status changes. |
| **Budget integration** | Missing | Dashboard shows "Budget requests in flight" KPI but commercial planner has no budget allocation, commitment, or draw-down flows. |
| **Multi-currency plan** | Missing | Each plan has a single `currency_code`. No support for multi-currency lines within one plan or automatic currency conversion across plans. |
| **Period management** | Missing | Plans have `period_start` and `period_end` but no period hierarchy (monthly/quarterly/annual breakdown), period locking, or period-over-period comparison within the planner. |

---

## 2. Gap Analysis

### Critical

| # | Gap | Impact | Location |
|---|-----|--------|----------|
| C1 | **Dashboard stock health renders raw JSON** | Users see `JSON.stringify` output for stock health — not actionable without visualization. | `apps/web/src/app/(app)/dashboard/page.tsx` L73-75 |
| C2 | **Plan status transitions have no validation** | Any status string is accepted by `PlanPatch`. A user can transition from "published" back to "draft" without controls, or set an invalid status. | `apps/api/app/api/v1/endpoints/commercial_planner.py` — `PlanPatch.status` accepts any string, validated only as `in ALLOWED_PLAN_STATUSES` on the PATCH handler but not enforced as a state machine. |
| C3 | **No approval workflow or audit trail for status changes** | There is no record of who changed a plan status, when, or why. In a commercial planning context this is a governance gap. | API `PATCH .../plans/{id}` — status is updated inline with no event log. |

### Medium

| # | Gap | Impact | Location |
|---|-----|--------|----------|
| M1 | **Line override UI incomplete** | Override fields for customer margin, distributor margin, VAT, FX, reserves exist in DB and are respected by the calculator, but the frontend only exposes override controlled cost in the line detail / waterfall. Users must use the API directly to set other overrides. | `page.tsx` — add-line and edit-line flows; `LineEconomicsWaterfall.tsx` — shows override_controlled_cost but not others. |
| M2 | **Suggestion confidence not prominently surfaced** | Suggestion cards show the confidence string but the `_meta.data_sources` (which fact tables contributed) are fetched but not visually displayed. Users cannot judge data freshness. | `page.tsx` — suggestion bundle rendering; `_meta` is in the type but not rendered. |
| M3 | **No export or download for plan lines** | Users cannot export plan lines (CSV/Excel) for offline review, sharing, or downstream systems. | Missing entirely. |
| M4 | **Environment / country picker not in create plan dialog** | The `Plan` type has `environment` and `country_code` fields, but the create-plan UI defaults to no picker for environment. Country code is a free-text field. | `page.tsx` — create plan dialog. |
| M5 | **Historical lineup multi-case merge not implemented** | Only single-case lineup sync is supported. No period-over-period comparison or merge of multiple lineup uploads. | `CurrentLineupSection.tsx` — sync-to-plan is per-case. |
| M6 | **Exceptions page has no link to commercial planner lines** | Exceptions are standalone rows with no foreign key or deep link back to the specific plan line or import job that triggered them. | `apps/web/src/app/(app)/exceptions/page.tsx` — flat list. |
| M7 | **No bulk inline edit for plan lines** | AG Grid cells support individual edits but there is no multi-select + batch update (e.g., set all selected lines to the same SRP or distributor). | `page.tsx` — grid edits are cell-level only. |

### Low

| # | Gap | Impact | Location |
|---|-----|--------|----------|
| L1 | **Plan currency label used inconsistently in column headers** | Some column headers say "(plan ccy)" while others use the actual currency code. When the plan currency changes, column header labels do not dynamically update in all cases. | `page.tsx` — optional column label definitions are static strings. |
| L2 | **Large page.tsx file (3,622 lines)** | Maintainability concern. The main page component contains the plan list, line grid, all dialogs, suggestion handling, lineup coverage, and data map tab — all in one file. | `apps/web/src/app/(app)/commercial-planner/page.tsx` |
| L3 | **Large API file (3,242 lines)** | Similar maintainability concern. All commercial planner endpoints in one file. | `apps/api/app/api/v1/endpoints/commercial_planner.py` |
| L4 | **localStorage version migration chains** | Four localStorage key versions (v1→v2→v3→v4) with migration logic. Works but adds complexity for a feature that could use server-side user preferences. | `page.tsx` — `LS_GRID_COLS_V*` constants and migration functions. |
| L5 | **CommercialDataMap is a static reference table** | Useful for developers but may not add value for business users in the production UI. Could be behind a developer/admin toggle. | `CommercialDataMap.tsx` |
| L6 | **Dashboard recommended_actions has no click handler** | The recommended actions panel renders titles and reasons but items have no navigation links or action buttons. The `href` field is in the type but not used. | `dashboard/page.tsx` L81-89 — no `<Link>` wrapper. |

---

## 3. Recommendations for Completion

### Immediate (pre-launch)

1. **Fix dashboard stock health visualization** — Replace `JSON.stringify` with a simple bar chart (Recharts is already a dependency) or structured key-value cards.
2. **Add plan status state machine** — Enforce valid transitions (draft→review→approved→published) and reject invalid moves in the API. Log status change events with timestamp and actor.
3. **Expose all line override fields in the UI** — Add override editors in the line detail panel for customer margin, distributor margin, VAT, FX, and reserves. These are already persisted and calculated.
4. **Add plan line export (CSV/XLSX)** — Allow downloading current plan lines with calculated economics. The data is already fully available from the GET endpoint.

### Near-term (next sprint)

5. **Surface suggestion data source metadata** — Render `_meta.data_sources` as small indicator chips (e.g., "sellout", "lineup", "pricing") so users know which fact tables contributed.
6. **Link exceptions to source** — Add `plan_line_id` / `import_job_id` foreign keys to exception rows and render deep links from the exceptions page.
7. **Make dashboard recommended_actions navigable** — Wrap each action in `<Link>` using the existing `href` field.
8. **Refactor page.tsx** — Extract the plan list, line grid, dialogs, and suggestion panel into separate feature components (similar to how `CurrentLineupSection`, `PlannerDefaultsMaintenance`, etc. are already extracted).

### Medium-term

9. **Multi-case lineup merge** — Support selecting multiple lineup cases and merging them into a single plan with conflict resolution.
10. **Period management** — Add monthly/quarterly breakdown within plan periods, with locking and comparison.
11. **Budget integration** — Connect commercial planner GP outputs to budget allocation and draw-down tracking.

### Deferred (per explicit design decisions)

12. **FX provider automation** — Requires external provider integration; current manual approach is intentional.
13. **True landed cost** — Requires logistics data modeling; explicitly scoped out.
14. **Pricing simulation** — Requires scenario engine; economics are currently single-point.

---

## 4. Broken Features / Inconsistencies

### No outright broken features found.

The commercial planner is functionally coherent within its current scope. However, the following inconsistencies were noted:

| # | Issue | Severity | Details |
|---|-------|----------|---------|
| I1 | **Dashboard `href` field unused** | Low | `recommended_actions` objects have an `href` string but the dashboard renders them as plain text, not links. Data returned from the API would include navigation targets that are silently ignored. |
| I2 | **ALLOWED_PLAN_STATUSES is a set, not an enum** | Low | `{"draft", "review", "approved", "published"}` is checked in the PATCH handler but `PlanPatch.status` is typed as `str | None`, allowing any value to pass Pydantic validation before reaching the handler check. A Pydantic `Literal` validator would catch this at the schema level. |
| I3 | **useMemo dependency in exceptions page** | Low | `colDefs` memo in `exceptions/page.tsx` line 63 includes both `delRow` and `delRow.isPending` in the dependency array. The `delRow` mutation object identity changes on every render in TanStack Query v5, which may cause unnecessary re-renders of the column definitions. The `isPending` check is sufficient. |
| I4 | **Legacy flag names in calculator** | Low | The calculator uses `missing_or_invalid_controlled_cost` while some trust/readiness code also checks `missing_or_invalid_landed_cost` (legacy). Both are handled but the dual naming could confuse future contributors. |
| I5 | **AddProductSetDialog creates lines sequentially** | Low | The batch creation loop in `handleCreate` sends one POST per product synchronously. For large product sets (50+), this could be slow. A batch API endpoint would be more efficient. |

---

## 5. Test Coverage

| Component | Tests | Notes |
|-----------|-------|-------|
| `EntitySearchAutocomplete` | 1 unit test | Covers server search load. |
| `CurrentLineupSection` | 5 unit tests | Covers open channel display, raw upload columns, discovered spec keys, UNASSIGNED distributor, entity resolution (open channel staging + customer-as-distributor redirect). |
| Commercial planner page | No dedicated tests | 3,622-line page has no unit/integration tests. |
| API `commercial_planner.py` | No dedicated tests found in audit scope | Would require `ALLOW_TESTS_ON_DEV_DB=1` per known gotchas. |
| Calculator (`calculator.py`) | Not checked in audit scope | Pure function — highly testable. |
| Economics trust | Not checked in audit scope | Pure functions — highly testable. |
| Suggestions | Not checked in audit scope | Pure functions with dataclass inputs — highly testable. |

**Recommendation:** Add unit tests for `calculator.py`, `economics_trust.py`, and `suggestions.py` as immediate wins — these are pure functions with no DB dependencies.

---

## Summary

The commercial planner is a **substantially built** module with deep economics calculation, trust classification, provenance tracking, lineup integration, and a rich frontend. The core plan → line → calculate → trust flow is coherent and well-integrated. The main gaps are around **governance** (status workflow, audit trail), **usability** (line override UI, export, dashboard visualization), and **scale** (multi-case merge, period management, budget integration). No broken features were found — the inconsistencies noted are minor and non-blocking.
