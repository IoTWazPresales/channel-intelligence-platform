# Promotion Planner Capability Audit — NS-6 Response


| Field | Value |
|-------|-------|
| **Document** | PROMO_PLANNER_CAPABILITY.md |
| **North-star** | NS-6 — Response (ranked commercial actions) |
| **Audit date** | 2026-08-30 |
| **Database** | cip on localhost:5432 (row counts measured on audit date) |
| **Branch context** | feat/ns-1a-fx-readiness-chips (code references current tree) |
| **Scope** | Data substrate, API contracts, tenant workbook parity — **no UI design** |
| **Out of scope** | Visual mocks (docs/design/*.html), operator journey wireframes |

---

## Executive summary

NS-6 **Response** is the commercial action queue: operators need enough signal to decide *which* promotions to run, *where* stock and sell-through support the window, *what* funding and terms allow, and *how* outcomes will be measured. This audit maps **what the platform can prove today** from live cip data and wired APIs versus what a promotion planner must consume.

**Headline:** CPOR case management, historical CPOR import, CST channel intelligence, demand forecast, and promo-plan **draft** APIs form a credible **partial** backbone. Critical gaps block a trustworthy end-to-end planner: **no customer×SKU cover series**, **empty budget and competitor facts**, **no promotion-performance fact writers**, **import/export column asymmetry**, and **no round-trip** from case export back through the tenant tracking workbook.

### Capability verdict rollup

| Capability lane | Verdict | One-line rationale |
|-----------------|---------|-------------------|
| Customer sell-through (CST) | **PARTIAL** | 1,823 fact rows, 8 customers, Mar 2024–Sep 2026; sparse accounts; no promo attribution on facts |
| Customer×SKU weeks of cover | **PARTIAL** | 179,463 distributor×product weeks_of_cover_observation rows; weeks_of_stock **0** rows; CST WoC is compute-on-read only |
| Promo performance / uplift | **PARTIAL** | 310 cases / 657 lines; 386 lines with estimate **and** result qty; fact_promotion_performance unused |
| Budget / funding envelope | **PARTIAL** | All fact_budget_* **0** rows; money ceiling uses portfolio + tenant profile, not ledger |
| Commercial terms and SKU assumptions | **PARTIAL** | 10 commercial_customer_term, 31 commercial_sku_assumption; not joined into draft ranking by default |
| Cost / DAP / economics | **PARTIAL** | Line cost basis + CP economics exist; DAP distinct from PM bottom; gaps on assumption coverage |
| Market / competitor context | **NOT AVAILABLE** | fact_competitor_price **0** rows |
| Seasonality / velocity | **PARTIAL** | 3,369 fact_customer_velocity rows (all carry seasonal_index); 38,625 fact_demand_forecast rows |
| Tenant workbook round-trip | **NOT AVAILABLE** | Export contract ≠ import contract (columns, sheets, dates) |
| Tenant export fidelity | **PARTIAL** | Case export wired (RESELLER_HEADERS, 32 cols); legacy promo export path still exists |

**Recommendation theme:** Prioritize **contract unification** (export profile ↔ asus_consumer_cpor_tracking_v1), **customer×SKU cover observations**, and **budget/competitor fact ingestion** before expanding Response UI ranking logic.

---

## 1. Scope and definitions

### 1.1 NS-6 Response (product)

From the CIP design packet, **Response** surfaces **ranked open commercial actions** (design mock: 6 actions). Capability for NS-6 therefore requires:

1. **Inputs** — sell-through, cover/stock, forecast, terms, cost, optional market pressure.
2. **Plan objects** — CPOR cases/lines (promotion windows, support, estimate/result qty).
3. **Governance** — budget/approval signals (even if advisory).
4. **Evidence loop** — export to tenant formats and reconcile results (promo load, settlement).

This document audits (1)–(4) at the **data + API** layer only.

### 1.2 Promotion planner in CIP

There is no single module named promotion_planner. Functionality is split across:

- **CPOR cases** (cpor_case, cpor_case_line) — primary promotion execution record.
- **Promo plan draft** (GET/POST /cpor/intelligence/promo-plan-draft*) — ranked suggestions → optional case creation.
- **Legacy promo tables** (dim_promotion, fact_promotion_plan, fact_promotion_performance) — largely scaffold.
- **Promo export** (promo_export service) — older CPOR workbook path parallel to case export.

NS-6 should treat **CPOR case + draft intelligence** as the planner spine unless product explicitly revives dim_promotion.

### 1.3 Verdict vocabulary

| Verdict | Meaning |
|---------|---------|
| **AVAILABLE** | Fact or API populated, wired, and grain matches planner need |
| **PARTIAL** | Some data or wiring; grain, coverage, or governance incomplete |
| **NOT AVAILABLE** | Empty facts, dead import handlers, or no API |

---

## 2. Evidence method

| Source | Use |
|--------|-----|
| SQL COUNT(*) on cip | Row counts, date ranges, distinct customers |
| Code inspection | Export headers, import profile, endpoint routers |
| Prior substrate audits | docs/PROMOTION_PLANNING_DATA_SUBSTRATE_AUDIT.md (code-only, 2026-06-14) |

Row counts in section 3 were **verified on the audit database** (current_database() = 'cip'). Code paths cited by repository path under apps/api/.

---

## 3. Database substrate inventory (cip)

### 3.1 Core fact counts

| Table / object | Rows | Notes |
|----------------|-----:|-------|
| fact_customer_sellthrough | **1,823** | **8** distinct customers; period_start_date **2024-03-25** → **2026-09-28** |
| weeks_of_cover_observation | **179,463** | Distributor×product observation series (BACKLOG-097) |
| weeks_of_stock | **0** | Derived table present; no materialized rows |
| cpor_case | **310** | Open/historical promotion cases |
| cpor_case_line | **657** | Line-level support economics |
| cpor_case_line (estimate and result qty) | **386** | Lines with both estimate_qty and result_qty populated |
| fact_budget_allocation | **0** | |
| fact_budget_commitment | **0** | |
| fact_budget_actual | **0** | |
| fact_budget_request | **0** | |
| fact_competitor_price | **0** | Market lens blocked |
| commercial_customer_term | **10** | |
| commercial_sku_assumption | **31** | |
| fact_customer_velocity | **3,369** | All rows include seasonal_index |
| fact_demand_forecast | **38,625** | DSI/customer forecast substrate |

### 3.2 Import staging evidence

| Metric | Value |
|--------|-------|
| Staged lines (CPOR historical import) | **26,313** |
| Active sheets | **Disti Sell out**, **Reseller Sell out** |
| Mapping profile | asus_consumer_cpor_tracking_v1 |
| header_row_index | **1** |

Staging volume confirms the tenant workbook is the **system of record** for historical promo truth; platform cases are a **subset** (310 vs thousands of staged lines).

### 3.3 Grain implications for NS-6

| Planner question | Best current grain | Gap |
|------------------|-------------------|-----|
| Who is selling? | CST: customer×product×period | Only 8 customers with facts |
| Do we have cover? | Distributor×product observations | Not customer×SKU; design packet uses customer×SKU pairs |
| What did we fund? | CPOR case lines | Budget facts empty |
| Did promo lift sell-through? | Case lines + CST window | No fact_promotion_performance; recon APIs exist per case |
| Vs competition? | — | No competitor prices |


---

## 4. Capability lanes (detailed)

### 4.1 Customer sell-through — **PARTIAL**

**Evidence:** 1,823 rows, 8 customers, multi-year weekly/monthly mix.

**Wired:** CST import → steward → act_customer_sellthrough; GET /api/v1/channel-intelligence compute-on-read velocity, aged inventory, trend.

**Gaps:**

- Coverage is narrow versus the full customer master.
- Facts do not carry promotion or case linkage — promo load recon is case-scoped API, not fact-attributed.
- currency_code on sell-through may be empty; CPOR recon assumes ZAR (see H-05).

### 4.2 Customer×SKU cover — **PARTIAL**

**Evidence:** weeks_of_cover_observation 179,463 rows at distributor×product; weeks_of_stock 0.

**Wired:** Reconstruct on DSI/shipment apply; Channel Ops / A3 read latest observation.

**Gaps:**

- NS-6 design language (PACKET_DATA.md) describes customer×SKU cover breaches (e.g. 119 pairs under 4w). Observation series does not match that grain without CST SOH plus velocity join.
- CST channel intelligence computes WoC on the fly — not persisted per customer×SKU.

### 4.3 Promo performance — **PARTIAL**

**Evidence:** 386 case lines with both estimate and result quantity.

**Wired:** CPOR case CRUD, recompute, promo-load recon, settlement paths.

**Gaps:**

- act_promotion_performance has no writers.
- promotion_plan import template remains stub_noop.
- PromoReadiness derived rows lack a live calculator service.

### 4.4 Budget — **PARTIAL**

**Evidence:** All budget fact tables 0 rows.

**Wired:** Read APIs on /budgets/*; CPOR money ceiling via commercial_tenant_profile plus portfolio spend.

**Gaps:** No allocation → commitment → actual chain populated.

### 4.5 Commercial terms — **PARTIAL**

**Evidence:** 10 customer terms, 31 SKU assumptions.

**Gaps:** Promo plan draft does not require assumptions before ranking; settlement already surfaces missing SKU assumptions on open cases.

### 4.6 Cost / DAP — **PARTIAL**

**Evidence:** CPOR lines store cost_basis, cost_source, support waterfalls; historical import maps Dealer System Cost and DAP columns.

**Gaps:** DAP must not be conflated with PM controlled cost or landed cost; import-only DAP columns are absent from export headers.

### 4.7 Market context — **NOT AVAILABLE**

**Evidence:** act_competitor_price count 0.

### 4.8 Seasonality — **PARTIAL**

**Evidence:** All 3,369 velocity rows include seasonal_index; 38,625 demand forecast rows.

**Gaps:** No promo elasticity model — seasonality adjusts baseline only.

### 4.9 Round-trip — **NOT AVAILABLE**

Export RESELLER_HEADERS (32 columns) vs import ASUS_COLUMN_MAP (39 fields), two channel sheets, Excel serial dates.

### 4.10 Tenant export — **PARTIAL**

pps/api/app/services/cpor/export_xlsx.py freezes header order; tests lock contract in 	est_cpor_export.py.


---

## 5. Import vs export contract

### 5.1 Export (case workbook)

| Property | Value |
|----------|-------|
| Module | pp.services.cpor.export_xlsx |
| Constant | RESELLER_HEADERS — **32** columns |
| Sheets | **Reseller**, **USD Pivot** |
| Semantics | Stored computed columns only — no waterfall recompute in export |

Representative headers: Case Code, Case Name, Customer, Promotion Type, Window Start, Window End, SKU, Distributor, Dealer Price, Support/Unit, Estimate Qty, Result Qty, Ttl Support USD, Flags.

### 5.2 Import (tenant tracking workbook)

| Property | Value |
|----------|-------|
| Profile | sus_consumer_cpor_tracking_v1 |
| header_row_index | **1** |
| Sheets | Disti Sell out, Reseller Sell out (pivot sheets ignored) |
| Column map | **39** canonical fields in ASUS_COLUMN_MAP |
| Dates | Excel serial numbers in source files |
| Staging | **26,313** lines |

### 5.3 Asymmetry summary

| Dimension | Export | Import |
|-----------|--------|--------|
| Column count | 32 | 39 mapped fields |
| Channel split | Single Reseller sheet | Disti + Reseller sheets |
| Header labels | English export contract (2026-07-09) | ASUS labels (Start From, Dealer/Retailer, …) |
| Extra import-only fields | — | Rebate %, disti margin, DAP invoiced, new DAP, disti ROE |
| Round-trip | — | **Not supported** |

---

## 6. API surface (promotion-relevant)

Base prefix: /api/v1 unless noted.

| Method | Path | Role for NS-6 |
|--------|------|----------------|
| GET | /channel-intelligence | CST velocity, WoC (computed), aged units |
| GET | /cpor/cases | Portfolio of promotion cases |
| GET | /cpor/cases/{id} | Case header and lines |
| POST | /cpor/cases | Create case |
| POST | /cpor/cases/{id}/lines | Add line |
| POST | /cpor/cases/{id}/recompute | Refresh line economics |
| GET | /cpor/cases/{id}/promo-load-recon | CST vs case window and price |
| GET | /cpor/intelligence/promo-plan-draft | Ranked promo suggestions |
| POST | /cpor/intelligence/promo-plan-draft/recompute | Rebuild draft |
| POST | /cpor/intelligence/promo-plan-draft/create-case | Materialize case from draft |
| GET | /cpor/intelligence/portfolio | Portfolio KPIs |
| GET | /cpor/intelligence/norms | Trailing support norms |
| GET | /cpor/intelligence/comparable-cases | Analog cases |
| GET | /cpor/intelligence/support-bias | Support bias diagnostics |
| POST | /cpor/cases/{case_id}/export | Tenant workbook export |
| GET | /cpor/cases/{case_id}/exports/{version}/file | Download export |
| GET | /cpor/historical-import/profiles | Mapping profiles |
| POST | /cpor/historical-import/jobs/{job_id}/apply | Bulk historical apply |
| GET | /promotions/plans | Legacy plan facts (read) |
| GET | /promotions/readiness | Legacy readiness (read) |
| GET | /budgets/allocations | Budget envelopes (empty DB) |
| GET | /budgets/health | Derived health (no facts) |
| POST | /query/execute | Metric cst_sellthrough_units |

Channel ops APIs expose distributor×product WoC observations — supply context, not customer×SKU Response cover.


---

## 7. Hardcoded tenant defects (H-01 – H-14)

These encode **ASUS Consumer CPOR** assumptions in code or frozen contracts. They block portable promotion planning until moved into versioned mapping profiles or tenant profile JSON.

| ID | Defect | Location / symptom | NS-6 impact |
|----|--------|-------------------|-------------|
| **H-01** | Frozen export header tuple | RESELLER_HEADERS in export_xlsx.py | Export layout cannot track profile without code change |
| **H-02** | Column cardinality mismatch | 32 export vs 39 import fields | Round-trip and validation diverge |
| **H-03** | Header label drift | Export English vs ASUS_COLUMN_MAP aliases | Workbook edits misalign with export names |
| **H-04** | Case currency default ZAR on historical apply | historical_import/apply_sync.py | FX readiness wrong for non-ZAR tenants |
| **H-05** | Assumed sell-out currency ZAR | cpor/config.py ASSUMED_SELLOUT_CURRENCY | Promo-load recon mislabels CST when currency empty |
| **H-06** | ASUS promotion-type map | ASUS_PROMOTION_TYPE_VALUE_MAP | New promotion types need deploy |
| **H-07** | Sheet role names hardcoded | ASUS_SHEET_ROLES | Renamed tabs break import |
| **H-08** | Dual CPOR export paths | promo_export/cpor_xlsx.py vs cpor/export_xlsx.py | Inconsistent workbooks |
| **H-09** | Empty weeks_of_stock | DB 0 rows vs observations | Wrong cover source if legacy readers used |
| **H-10** | Dead promotion_plan import | stub_noop in template_definitions | Cannot ingest plan files to dim_promotion |
| **H-11** | Module tenant policy defaults | commercial_tenant_profile.py | New tenants inherit ASUS money-axis rules |
| **H-12** | Import-only columns absent from export | DAP invoiced, rebate, disti margin | Export loses tracking-sheet fields |
| **H-13** | Excel serial vs native datetime | Import parser vs openpyxl write | Round-trip date failures |
| **H-14** | header_row_index: 1 default | sus_consumer_cpor_tracking_v1 | Title rows above headers break mapping |

---

## 8. NS-6 Response readiness matrix

| Response action archetype | Minimum data | Status |
|---------------------------|--------------|--------|
| Fund promo on weak cover customer×SKU | CST + customer×SKU WoC | **Blocked** — wrong WoC grain |
| Fund promo with budget guardrail | Budget facts + case spend | **Partial** — ceiling only |
| Prioritize by forecast gap | act_demand_forecast | **Available** (volume) |
| Prioritize by seasonality | seasonal_index on velocity | **Partial** |
| Compare to market | act_competitor_price | **Blocked** |
| Draft case from ranking | promo-plan-draft API | **Partial** |
| Publish tenant tracking sheet | case export | **Partial** — H-01–H-03 |
| Close loop on results | estimate vs result qty | **Partial** — 386 lines |
| Steward historical promos | CPOR historical import | **Partial** — 26k staged lines |

---

## 9. Dependencies on other north-star modules

| Module | Dependency |
|--------|------------|
| NS-3 Stock / Cover | Customer×SKU cover; observations are distributor×product |
| NS-4 Settlement | Case FX and assumptions block funding |
| NS-5 Lineup | Planned units vs fill — planner must not contradict lineup |
| Steward | CPOR/CST import queues — bad mappings poison rankings |

---

## 10. Recommendations (prioritized)

### P0 — Contract and truth

1. Unify export headers with sus_consumer_cpor_tracking_v1; store export_schema_version on exports.
2. Deprecate or alias legacy promo_export/cpor_xlsx.py (H-08).
3. Persist customer×SKU cover observations or document CST compute-on-read as the NS-6 cover contract.

### P1 — Facts for ranking

4. Ingest budget allocations or hide budget verbs until facts exist.
5. Competitor price import or permanent data_unavailable on market lane.
6. Surface commercial_sku_assumption gaps in promo-plan-draft (mirror settlement).

### P2 — Performance loop

7. Backfill act_promotion_performance from case lines + CST windows, or retire scaffold table.
8. Revive promotion_plan import only if product commits to dim_promotion.

### P3 — Tenant portability

9. Move H-06, H-07, H-14 into DB profiles — code ships generic engine only.
10. Round-trip acceptance test: export case → profile transform → re-import diff.

---

## Appendix A — Key code references

| Topic | Path |
|-------|------|
| Export headers | pps/api/app/services/cpor/export_xlsx.py |
| Import profile | pps/api/app/services/cpor/historical_import/profile_defaults.py |
| Promo plan draft | pps/api/app/services/cpor/promo_plan_builder.py |
| CST read model | pps/api/app/services/channel_intelligence/cst_read_model.py |
| Tenant policy | pps/api/app/services/commercial_tenant_profile.py |
| Substrate audit | docs/PROMOTION_PLANNING_DATA_SUBSTRATE_AUDIT.md |
| Design packet | docs/design/PACKET_DATA.md |

---

## Appendix B — SQL snippets (reproducibility)

sql
SELECT current_database();
SELECT COUNT(*) FROM fact_customer_sellthrough;
SELECT COUNT(DISTINCT customer_id) FROM fact_customer_sellthrough;
SELECT MIN(period_start_date), MAX(period_start_date) FROM fact_customer_sellthrough;
SELECT COUNT(*) FROM weeks_of_cover_observation;
SELECT COUNT(*) FROM weeks_of_stock;
SELECT COUNT(*) FROM cpor_case;
SELECT COUNT(*) FROM cpor_case_line;
SELECT COUNT(*) FROM cpor_case_line WHERE estimate_qty IS NOT NULL AND result_qty IS NOT NULL;
SELECT COUNT(*) FROM fact_budget_allocation;
SELECT COUNT(*) FROM fact_competitor_price;
SELECT COUNT(*) FROM commercial_customer_term;
SELECT COUNT(*) FROM commercial_sku_assumption;
SELECT COUNT(*) FROM fact_customer_velocity;
SELECT COUNT(*) FROM fact_demand_forecast;


---

*End of audit.*

