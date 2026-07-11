# BACKLOG-074 U4 — Ops / admin grid parity inventory

**Unit:** U4 (docs-only)  
**Purpose:** Inventory matrix for ops/admin surfaces **outside** the U-G1 Theme B master-grid scope (`BACKLOG-061-U4_master_grid_capability_matrix.md`).  
**Review gate:** Review before any follow-up units that adopt `MasterDataGridShell` or extend the CST Unit 3/3b composed-chrome baseline.  
**Scope:** Docs only — no app code changes in this unit.

**Reference (do not duplicate):** `docs/design/BACKLOG-061-U4_master_grid_capability_matrix.md` — Customers / Products / Distributors and `MasterDataGridShell`.

**CST baseline (Unit 3 + 3b — gap-column reference):**
- `GET /api/v1/cst-steward/key-accounts` and `GET /api/v1/cst-steward/article-aliases` return `{ items, total }` with `limit` (default 100, le=500) / `offset`.
- UI: `ModuleGridToolbar` + `ModuleDataSection` + tab-0 `MasterColumnPickerDialog`; Prev/Next + `page` / `page_size` URL params.
- **No** `MasterDataGridShell` swap on CST steward.

`MasterDataGridShell` usage today: **only** `admin/customers`, `admin/products`, `admin/distributors` — **none** of the rows below.

---

## 1. Executive summary

| Surface | Server pagination | UI pagination | Composed chrome | Column picker + LS | Primary scale risk |
|---------|-------------------|---------------|-----------------|--------------------|--------------------|
| Plan vs Executed | No (single payload) | Client AG Grid (15/20) | Partial (`ModuleDataSection` drill only) | None | Full exception lists in one response |
| CPOR cases | No | None | None | None | Unbounded case list + N+1 lines |
| Product Master gaps | Cap only (`limit` 2k–5k) | None | Partial (`ModuleDataSection`) | None | Silent truncation at 2k tokens |
| Channels & Regions | No (full dim lists) | None | Yes (`CatalogDimensionGridPanel`) | None | Low cardinality today |
| Channel Operations | Mixed | MUI `Table` (fixed page 1) | None | None | Sell-out/movements UI ignores paging |
| PO Management | No (derived groups) | Gap grid auto-height | None | None | Full backlog/gap payloads |
| Inbound shipping | Yes (`skip`/`limit`) | `TablePagination` | Yes | Bespoke dialog + LS | `filter-options` cap 8k–20k |
| Shipment evidence | Yes (`skip`/`limit`) | `TablePagination` | Yes | Bespoke dialog + LS | Change-events cap 500–5k |
| CST steward | Yes (accounts + aliases) | Prev/Next URL | **Baseline** | Tab 0 only | Slots worklist unpaginated |

---

## 2. Inventory matrix (detail)

### 2.1 Plan vs Executed (PVE)

| Column | Detail |
|--------|--------|
| **Route(s) + page** | `/plan-vs-executed` → `apps/web/src/app/(app)/plan-vs-executed/page.tsx` → `PlanVsExecutedView.tsx`; `ExceptionCategoryGrid.tsx` |
| **List API + contract** | `GET /api/v1/plan-vs-executed` — **not paginated**. Params: `period_from/to`, `product_line`, `rank_by`, `product_group_by`, drill filters. Service comment: *"full list; UI paginates"*. |
| **Grid** | **Bespoke** — `EnterpriseDataGrid` + `ModuleDataSection` (drill). No toolbar / shell. |
| **Column picker + LS** | None |
| **Export / bulk** | None (deep-links to PO Management / shipping) |
| **Scale risks** | Entire ranked exception sets per request; client page size does not shrink payload |
| **Gap vs CST + size** | Missing URL list state, toolbar, column picker, server paging. **M** |

### 2.2 CPOR cases

| Column | Detail |
|--------|--------|
| **Route(s) + page** | `/commercial-planner/cpor-cases` + `/[id]` — list + Lines / pivot / Events / Exports / Settlement tabs |
| **List API + contract** | `GET /api/v1/cpor/cases` → **raw array**, no envelope, **no pagination**; `list_cases` loads lines per case (N+1) |
| **Grid** | **Bespoke** bare `EnterpriseDataGrid` |
| **Column picker + LS** | None |
| **Export / bulk** | Per-case XLSX export; line CRUD; claim import |
| **Scale risks** | Unbounded list; detail embeds all lines |
| **Gap vs CST + size** | No chrome, no pagination. **M** (list first; detail lines follow-up). Contract change, not schema. |

### 2.3 Product Master gaps

| Column | Detail |
|--------|--------|
| **Route(s) + page** | `/admin/product-master-gaps` → `ProductMasterGapWorklistView.tsx` |
| **List API + contract** | `GET /api/v1/product-master-gaps/worklist` → `{ rows, total, truncated }` — `limit` default **2000**, max **5000**, **no offset** |
| **Grid** | **Bespoke** — `EnterpriseDataGrid` + `ModuleDataSection`; always-on checkboxes |
| **Column picker + LS** | None |
| **Export / bulk** | Scan / preview / confirm-apply |
| **Scale risks** | Silent truncation at 2k (`truncated: true`); full set held client-side for selection |
| **Gap vs CST + size** | Has data section; needs toolbar + offset paging + URL state. **M** |

### 2.4 Channels & Regions + Channel Operations

#### 4a. Channels & Regions (`/admin/channels-regions`)

| Column | Detail |
|--------|--------|
| **API** | `GET /api/v1/catalog/channels|regions` — full arrays, no `.limit(` |
| **Grid** | **Composed** — `CatalogDimensionGridPanel`: toolbar + `ModuleDataSection` + bulk delete. **Not** shell. |
| **Gap + size** | Optional shell if dims grow. **S** (low urgency) |

#### 4b. Channel Operations (`/sell-out`)

| Column | Detail |
|--------|--------|
| **API** | `/channel-ops/summary`, `/weekly-series`, `/sell-out` (page/page_size le=500), `/inventory`, `/movements` |
| **Grid** | **Bespoke MUI `Table`** — not AG Grid; sell-out/movements UI often fixed `page=1&page_size=50` with no forward control |
| **Gap + size** | Different surface class. **L** — phased paging UI; defer AG Grid |

### 2.5 PO Management

| Column | Detail |
|--------|--------|
| **Route(s) + page** | `/admin/po-management` → `PoManagementView.tsx` + `PoAutoLinkProposalsSection.tsx` |
| **API** | `/po-management/coverage|backlog` — unpaginated groups; gap worklist full payload; auto-link `limit` default 500 |
| **Grid** | Backlog = **cards**; gap = `EnterpriseDataGrid` auto-height; auto-link = MUI tables |
| **Gap + size** | Paginate gap + auto-link; wrap gap in `ModuleDataSection`. **M** |

### 2.6 Inbound shipping + shipment evidence

#### 6a. `/shipping`

| Column | Detail |
|--------|--------|
| **API** | `GET /api/v1/shipping/lines?skip=&limit=` → `{total, skip, limit, items}` (le 500). `filter-options` le 20k |
| **Grid** | **Composed** — toolbar + `ModuleDataSection` + `TablePagination` |
| **Column picker** | Bespoke `InboundShipmentsColumnsDialog`; LS `cip.commercial.inbound-shipments.grid.optional.v1` |
| **Gap + size** | Align picker with `MasterColumnPickerDialog`; URL-sync skip/limit. **S** |

#### 6b. `/admin/shipment-evidence`

| Column | Detail |
|--------|--------|
| **API** | `GET /api/v1/shipment-evidence?skip=&limit=` (le 1000) |
| **Grid** | Same composed stack as inbound |
| **Column picker** | Bespoke `ShipmentEvidenceColumnsDialog`; LS `cip.admin.shipment-evidence.grid.v1` |
| **Gap + size** | Shared optional-column pattern with inbound. **S** |

### 2.7 CST Steward (baseline)

| Column | Detail |
|--------|--------|
| **Route** | `/admin/cst-steward` → `apps/web/src/app/(app)/admin/cst-steward/page.tsx` |
| **API** | key-accounts + article-aliases: `{items,total}` + limit/offset. Slots worklist: **unpaginated** |
| **Grid** | **Composed baseline** — no shell |
| **Column picker** | Tab 0: `cip.admin.cst-steward.key-accounts.grid.v2` |
| **Remaining gap** | Slots pagination; aliases column picker. **S** |

---

## 3. Cross-cutting findings

1. **Two pagination dialects:** shipping/evidence use `skip`/`limit`; CST / channel-ops use `offset`/`limit` or `page`/`page_size`. Do not invent a third.
2. **Column pickers:** Theme B + CST tab 0 use `MasterColumnPickerDialog`; inbound/shipment use bespoke `*ColumnsDialog` — parallel patterns.
3. **Composed chrome without shell** is proven (CST, inbound, channels-regions). Shell remains optional for non-master lists.
4. **Schema:** nothing here requires new tables for grid parity (**FLAG** only if product asks for persisted views / export audit tables).

---

## 4. Recommended unit order (ranked, separately shippable)

| Rank | Unit | Size | Rationale |
|------|------|------|-----------|
| **1** | **U4a — CST slots + aliases parity** | S | Finish baseline: paginate slots worklist; aliases column picker |
| **2** | **U4b — Inbound + shipment evidence column/URL alignment** | S | Already paginated; converge picker + URL-sync |
| **3** | **U4c — Product Master gaps server paging + toolbar** | M | Live truncation at 2k is steward data-integrity UX |
| **4** | **U4d — CPOR case list pagination + composed chrome** | M | Worst unbounded list + N+1 smell |
| **5** | **U4e — PO Management gap grid + auto-link scale** | M | Operational triage scale |
| **6** | **U4f — Plan vs Executed exception API paging** | M | Payload-heavy read-only; charts unchanged |
| **7** | **U4g — Channel Operations sell-out/movements paging UI** | L | Different paradigm; defer |
| **8** | **U4h — Channels & Regions shell optional** | S | Low urgency |

**Explicit non-goals:** `ColumnSelectorModal`; DSI steward checkbox semantics; `MasterDataGridShell` on CST; schema/alembic without approved migration unit; mega-PR bundling PVE/CPOR/PO/inbound.

---

## 5. Open questions (non-blocking)

1. Share one optional-column module for inbound + shipment evidence, or keep page-local?
2. PVE: server-side exception pages vs cap + “show more” per category?
3. Channel Ops: AG Grid parity or paginated MUI tables with shared toolbar?
4. PO backlog cards: stay non-grid forever?

---

## 6. Acceptance anchors (docs review)

- [x] Every scope row present with real paths
- [x] CST 3/3b baseline accurate (no shell; `{items,total}` on key-accounts + aliases)
- [x] No duplication of BACKLOG-061 master-grid matrix
- [x] Ranked units independently shippable
