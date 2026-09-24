# N-0040 discovery: every product line is a sellable BU (D-g)

Seat: discovery (architecture-specialist, domain-analyst, data-quality-governance-specialist). Read-only. SQL ran against `cip` with a read-only session via `n0040/q.py`. 2026-09-24.

## 1. Hits (non-test source; apps/api, apps/web)

| # | file:line | Kind | Defect under D-g? | Replacement |
|---|---|---|---|---|
| H1 | api `services/commercial_planner/lineup_business_unit_resolution.py:33` `CANONICAL_SHEET_BU_CODES={NB,NR,NX,NV}` | BU derivation, sheet and folder tiers (3 and 4); the default whenever `tenant_bu_codes` is None | **Yes, and live.** Omits PF and XB even though lineup cases use both | `sellable_line_codes(db)` = `SELECT DISTINCT trim(product_line) FROM dim_product WHERE product_line IS NOT NULL AND trim(product_line)<>''` |
| H2 | api `.../lineup_backfill_archive_config.py:14` `DEFAULT_ACZA_TENANT_BU_CODES={NB,NR,NV,NX,PF,XB}` | Archive folder-segment classifier (default for config) | Yes | The same service. The config field stays as an optional override |
| H3 | api `endpoints/commercial_planner.py:3898` → `execute_bulk_lineup_preview` | Leaves out `tenant_bu_codes`, so the preview resolves with H1's four codes | **Yes (plumbing gap).** A `PF\2025\Q1` or `XB\...` folder is not recognised on the server | Load the codes once per request and pass them down |
| H4 | api `.../lineup_case_parser.py:761` `resolve_lineup_business_unit(...)` | Single-file import; no `tenant_bu_codes`, so it uses H1 | Yes | Same as H3 |
| H5 | api `.../lineup_period_inference.py:21` `CANONICAL_PRODUCT_LINES={Gaming,Consumer,NV,NB}` and `:199-213` filename fallback | Case `product_line` fallback when fewer than 25% of rows resolve | **Yes.** It emits `Gaming` and `Consumer`, which are not `product_line` values. The constant is referenced only by a test | Match filename tokens against the data-driven code set and drop the words |
| H6 | api `services/imports/pm_mapping_memory.py:19-34` `PM_PRODUCT_LINES` (the 14 observed codes, hardcoded) → `endpoints/imports_product_master.py:194` | PM import line chips (filter options) | Yes. The set is correct today but frozen | The service result, not a constant |
| H7 | web `app/(app)/admin/imports/BulkLineupBackfillDialog.tsx:55` `TENANT_BU_OPTIONS` (6 codes) used at `:640` | BU override `<select>` options | Yes. A steward cannot pick PT, LM, PD, etc. | Options from the new endpoint |
| H8 | web `features/commercial-planner/lineupBackfillArchivePath.ts:3` `DEFAULT_TENANT_BU_CODES` (6 codes, mirrors H2) | Client-side archive path parser | Yes | Codes passed in from the endpoint. The default parameter is kept only for tests |
| H9 | web `BulkLineupBackfillDialog.tsx:389,410` copy "NB/NR/…", "NB/NR/NV/PF/XB subfolders" | Label or help text | Minor defect (copy) | Neutral wording: "product-line folders" |
| H10 | web `features/supply-inbound/InboundShipmentsWorkspace.tsx:636` Plan BU free text, "e.g. NB" | Filter | Not a hardcoded set, but has no picker | Optional: a select fed by the endpoint |
| H11 | api `plan_vs_executed.py:568` text "(e.g. NB/NR/NV/NX)"; `lineup_business_unit_resolution.py:334` docstring "NB/NR/NV/PF/XB" | Reason string / docstring | Wording only | Neutral wording |
| L1 | api `po_management.py:36` `canonical_product_line_code`, `inbound_lineup_quarter.py:293,416,565`, `load_business_unit_by_product_id` (`:333`, reads `product_line`) | Grouping, filter, product tier | **Legitimate**, already data-driven | None |
| L2 | web `PlanVsExecutedView.tsx:329` `buOptions` from `drill_rows` | Filter options | Legitimate (data-derived, from loaded rows only) | Optional: the endpoint |
| L3 | `design-lab/**` fixtures; api `scripts/ops/*` clone proofs | Fixtures, one-off scripts | Legitimate | None |
| T | tests: `test_lineup_period_inference.py:110` asserts the H5 set; `test_lineup_business_unit_resolution.py:146` uses sheet "PF"; web `lineupBackfillArchivePath.test.ts` | Fixtures | They pin defects H5/H8 | Update them with the fix |

No DB check constraints or enums on `product_line` or `business_unit` (checked with `pg_constraint` and `pg_enum`). There is no "five" wording in code. The five-line set exists only as data (`commercial_lineup_case` = NB, NR, NV, PF, XB). Three different hardcoded sets exist today (4, 6 and 14 codes) plus a fourth in docs (`COMMERCIAL_SEMANTICS.md` A1-07, NB/NR/NV/NX).

## 2. Lineup supersession

- The key is period | customer | BU (`lineup_period_canonical.py:156`). Collisions: `lineup_bulk_backfill_preview.py:591` and `:674`. Applied at `lineup_bulk_backfill_apply.py:389-444` and in `lineup_case_supersession.py`.
- **Supersession does not read a BU set itself.** It depends on the set only indirectly, through the BU value that H1/H2 produce in resolver tiers 3 and 4. Tier 1 (product, ≥25% of rows resolved) already uses every `product_line`. Manual override accepts any string.
- Current data (cip): 44 cases. 35 have no stored `lineup_bu_resolution` (bulk path) and 1 is tier `product`. For every active line, the case BU equals the product's `product_line`: NB 1573, NR 746, NV 59, PF 137, XB 127, plus 61 lines with no product. There are 7 supersession pairs (9→122, 119→120, 130→146, 141→117, 142→133, 143→136, 144→121), and in all 7 the winner BU equals the loser BU.
- **Prediction: 0 existing cases or supersession links change.** `superseded_by_case_id` is persisted and nothing recomputes it. The fix changes only future previews in which fewer than 25% of rows resolve and the sheet or folder names a code outside the old set. PF and XB folders would resolve on the server instead of falling to `_unresolved` or needing a manual pick. That can create new collision groups on re-import. Per D-g, this must be proven on a clone: re-run the preview for the archive tree before and after, and diff proposals, BU, collision groups and planned units per period/BU. `prove_duplicate_partition_repair_clone.py` has the harness shape.
- **Risk (finding):** widening the sheet tier to 14 codes makes tabs named `AI`, `PT`, `LM`, `PD` or `CB` claim a BU. Keep the `bu_label_product_mismatch` flag, and apply the label tier only when the product tier fails, as now.

## 3. NULL product_line (10 rows): test pollution, not real products

| id | sku | name | category |
|---|---|---|---|
| 1 | SKU-ALPHA-01 | Alpha Pro 200 | Audio |
| 70820 | SKU-HL-01 | Hist Product | Audio |
| 70821–70828 | SKU-RES-01…07, SKU-STEP2-TEST, SKU-RES-ILIKE | "Resolution … Product", "ILIKE-TESTSENTINEL-2026-PRODUCT" | NB |

All 10 have `business_unit` NULL. The only fact use is **1 `cpor_case_line`** (id 1, case 4). The other 8 tables checked have 0. Surfaces: PO grouping puts them in "Unclassified" and plan-vs-executed in "(unassigned)". `channel_ops.py:1037` falls back to `category` (8 as "NB", 2 as "Audio"). The resolver skips them, and the new list source excludes them. Recommend a steward decision to retire them, plus a data-quality flag for new NULL rows.

## 4. The 16-vs-14 count

Measured: **14 distinct values**, with no trim or case variants. Counting NULL gives 15. There is one tenant. The other tables are narrower: lineup cases have 5 values, CPOR staging 6 plus NULL, shipment evidence 8, and CPOR lines 5 plus NULL.

Two sources plausibly give **16**:
- (a) `catalog_product` snapshot `base_unit`, parsed at chars 3–4, gives the 14 codes plus `-9` (108 `VP-9N…` NB rows) plus `-X` (38 `90-XB…` XB rows).
- (b) The 14 codes plus NULL plus the "Unclassified" display bucket.

Which one Warren meant is UNKNOWN. The code must not depend on the count. Side finding: the catalogue line disagrees with `dim_product` for 26 products.

## 5. Proposed implementation

1. **One source (API).** New `app/services/catalog/product_lines.py`, `list_sellable_product_lines(db)`: distinct, trimmed, non-null values, ordered by product count. It uses a TTL cache that is invalidated after PM commit. Optional display labels come from a tenant-profile key `product_line_labels` and are never used for membership. Endpoint `GET /api/v1/catalog/product-lines` returns `[{code, product_count, label}]` and `null_product_line_count`.
2. **API.** Remove the H1/H2 constants: `_bu_codes(None)` calls the service. Plumb the codes through H3 and H4. Make H5 data-driven. H6 uses the service.
3. **Web.** A shared `useProductLines()` hook feeds H7 and H8 and the PM chips. Fix the H9/H11 copy.
4. **Tests.**
   - Service: NULL and blank values excluded.
   - Resolver: PF, XB and PT resolve through the sheet and folder tiers.
   - Replace the H5 assertion.
   - Archive-path test with injected codes.
   - Dialog options rendered from a mocked endpoint.
   - A guard test that fails on literal BU code sets outside tests and fixtures.
5. **Proof (D-g).** Run the bulk preview over the archive on a clone, before and after. Diff BU per proposal, collision groups and planned units per period/BU. Expect 0 persisted changes.
6. **Defer.** NULL-row cleanup (steward). The `COMMERCIAL_SEMANTICS.md` A1-07 PM grain (NB/NR/NV/NX). The `dim_product.business_unit` division anomalies (8 "NB", 2 "NR").
