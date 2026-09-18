# Outbound read API — specification

**Status:** spec only. No endpoints, models, or migrations in the session that wrote this.
**Date:** 2026-09-18
**Audience:** Power BI, Tableau, Grafana, and a tenant warehouse that must survive CIP schema change.

Claims below are **VERIFIED** against the tree and `cip` unless marked **ASSERTED**.

---

## Two products, not one pipe

CIP today is an operator application. BI consumers need a **versioned read contract**.
Raw tables are not that contract. They contain provisionals (`TMP-CUST`), soft-redirected
merged records (`merged_into_*`), `raw_source_row` JSONB, steward state, and they move
with Alembic.

Deployment is **one CIP instance per company**. A tenant may later grant a **partner org**
scoped access (distributor, retailer, HQ finance). Auth and scoping are required on day
one of this API. Bolting them on after first consumers land will fork the contract.

---

## What already exists (VERIFIED)

| Surface | Path | What it is | Why it is not the outbound contract |
|---|---|---|---|
| Governed query engine | `POST /api/v1/query/execute`, `POST /api/v1/query/explain` | Metric + grains + filters → validated handler. Catalog in `apps/api/app/semantics/catalog/default.yaml` (fill_rate, weeks_of_cover, support_spend, volume_bias, …). | Auth is `get_optional_current_user`. Missing user → `tenant_id = default`. Not versioned. Shape can change with the app. |
| Saved reports | `/api/v1/saved-reports` | Operator-owned report defs. | Human UI persistence, not a partner SLA. |
| Dashboards | `/api/v1/dashboards` | Widget layout over the same engine. | Same. |
| Report export / delivery | `/api/v1/reports` · `report_export.py` · `report_delivery.py` · tables `report_delivery`, `report_schedule` | XLSX/PDF of a governed metric, with data vintage on the cover, inbox + cadence. | File drop for people. Not a live BI feed. Formats `xlsx`/`pdf` only. |
| Domain GETs | `/products`, `/customers`, `/distributors`, `/sellout`, `/shipping`, `/cpor`, `/plan-vs-executed`, `/channel-ops`, … | Operator read models. Mix derived fields, steward flags, `data_unavailable`. | Unstable, session-auth stub (`cip_auth_mode=stub` on this host), no partner scope. |
| SQL viewer | `/api/v1/admin` SQL | Admin escape hatch. | Must never be the BI path. |

IAM today (`app_user.role`): `admin` / `steward` / `planner` / `viewer`. No partner role.
No user↔product_line mapping. Tenant column exists on some tables (`tenant_id`, default `"default"`).

---

## Contract (to build)

**Name:** CIP Read API
**Base:** `/api/v1/read/v1/`
**Stability rule:** additive within `v1`. Breaking change → `v2` with overlap. Schema
migrations underneath do not change resource names, grains, or enums the consumer sees.

### Auth (day one)

- Session or PAT. No optional-user fallthrough. No forgeable `X-User-Role`.
- Every token is `{ tenant_id, principal, scopes[] }`.
- Scopes are **resource + grain**, not “admin”.
  Examples: `read:stock`, `read:plan_vs_executed`, `read:funding.settled`, `read:masters.product`.
- Partner grant: a tenant admin binds an external org to a subset of
  `distributor_id[]` and/or `customer_id[]` and/or `product_line[]`.
  The API never returns a row outside that grant. **ASSERTED** need: Warren must decide
  whether partner orgs are first-class principals or just scoped tokens.

### What is in the contract vs what is not

**In:** current-truth dimensions and facts after steward apply; governed metrics;
explicit `as_of` / data vintage; merge redirects already applied (survivor id only).

**Out:** `TMP-*` provisionals, `needs_review` candidates, `raw_source_row`,
`import_job` / mapping-queue rows, `product_attribute_value`, cancelled/superseded
cases unless the resource is explicitly `include_superseded=true`.

### Resources and grain

BI consumers actually need these, not a table dump:

| Resource | Grain | Notes |
|---|---|---|
| `products` | one row per canonical `dim_product` (survivor) | sku, part_number, names, `product_line`, division `business_unit`, lifecycle, ean/upc, `is_active`. Specs as a versioned JSON map from `specs_json`, not EAV. |
| `customers` | one row per survivor `dim_customer` | Exclude TMP and merged-away ids. Include group / strategic flags. |
| `distributors` | one row per survivor `dim_distributor` | Same merge rule. |
| `sellout` | distributor × product × period (week) | From `fact_sales_sellout` current truth. Quantity only; no staging. |
| `inventory_channel` | distributor × product × as-of | Derived SOH — never a stored SOH fact presented as truth. |
| `inbound` | shipment line current truth | Lifecycle state, qty, dates. No evidence JSONB. |
| `lineup_plan` | case × customer × product × period | Confirmed plan lines only for default; draft behind a flag. |
| `cpor_case` | case | Window, type, commercial status (`ended` / `settled`). Do not emit paid until a paid state exists. |
| `cpor_case_line` | case × product × distributor | Estimate, result, support. Flags stay flags. |
| `metrics` | POST body: metric key + grains + filters + `as_of` | The existing query engine, frozen under `/read/v1/metrics/execute`. Same catalog keys. |

Period grain for time series: ISO week Monday, month, quarter — already the query engine’s
`period_grain`. Do not invent a fourth calendar.

### Versioning

- URL version `v1`.
- Catalog version header `CIP-Semantics: 2026-09` (date of the frozen metric catalog).
- Each list page: `as_of`, `vintage` (max source job completed_at), `partial: boolean`.
- Soft-delete / merge: `replaced_by` on masters when a survivor exists; never leak loser ids
  into facts.

### Size

Several sessions to ship v1 (auth + grants + 8 resources + metrics facade + pagination +
vintage). A programme if partner-org grants and warehouse CDC are in the same slice.
Do not build CDC until v1 lists are stable.

### Decisions Warren must make

1. First consumer: warehouse dump, Power BI DirectQuery, or Grafana metrics-only?
2. Partner grants in v1, or tenant-internal tokens only until a named partner exists?
3. Default `product_line` filter for a PM token — all lines, or named BUs (NB/NR/NV/PF/XB)?
4. Settled vs paid: outbound `cpor_case.status` stays the commercial enum until a paid
   state is migrated (see settlement spec). Do not publish “paid” as settled.
5. Specs: include `specs_json` on `products`, or a separate `product_specs` resource?

---

## Explicit non-goals

- Wrapping SQL viewer.
- Exposing `catalog_product` / `attribute_definition` / `product_attribute_value`.
- Re-enabling `PM_WRITE_LEGACY_EAV`.
- Per-vendor Amazon/Tableau connectors on the way out.
