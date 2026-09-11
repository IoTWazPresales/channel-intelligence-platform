# N-0018 Supply & Inbound coverage map

**Source (lab, primary):** `apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx` `SupplySurface` + `apps/web/src/design-lab/shell/labNav.ts` domain `supply`. Lab page `apps/web/src/app/(design-lab)/design-lab/supply/page.tsx` always renders `SupplySurface` and **ignores** `?lens=`.

**No attached cross-check** was present in the implement chat. This map is lab SOURCE vs production SOURCE (routes, nav, APIs, `cip` SQL). Frozen design-language HTML and `.eif/audit/**` grammar numbers are not cited.

**NUMBER RULE** (`current_database()=cip`, tz `Africa/Johannesburg`, measured 2026-09-07 Monday). Lab figures are class **(i) fixture**. Production headlines must be class **(iii)** from `fact_inbound_shipment` / `purchase_order` with honest captions. Do not change a number to make lab and production agree.

| Headline / chart | Lab fixture (i) | Production grain | cip (iii) | Class |
|---|---|---|---|---|
| Open shipments | 388+296 shipped+arrived | `status ≠ received` (same as Brief `inbound_open`) | **1964** lines | (iii) |
| Unreceived past ETA | 1714, oldest 41d | `pod_date` null and `eta_date` < today SAST | **770**, oldest **123d** (eta 2026-05-07) | (iii) |
| Received this week | 312, “ASN 2026-09-01 applied” | `pod_date` in current ISO week (Monday SAST) | **0** (Monday) | (iii) |
| PO coverage | 79% “plan units covered” | Observed POs vs linked to an **active** lineup case (`po_management.coverage`) | **322 / 2308** (~14%) | (iii) linked/observed; **not** plan units |
| Backlog units | sum of fixture `poCoverage.backlogUnits` = 16050 | `line_state = open_order` units | **118024** | (iii) |
| Lifecycle chart | 5 fixture bars including Arrived + Unreceived | Code `lifecycle_bucket`: landed / pipeline / shipped | landed **13065**, pipeline **1635**, shipped **329** | (iii) **three disjoint** bars |
| Commercial overdue | not in lab | `predicate_overdue` (scheduled, promise window, ETA still incoming) | **546** (narrower than 770) | do not swap 770 for overdue |

`line_state` values on cip: `shipped`, `open_order` only. **Arrived is not a stored state.** Unreceived-past-ETA **overlaps** pipeline+shipped — not a fifth disjoint bar.

---

## Lab routes

| Route | Lab SOURCE | Production analog | Coverage |
|---|---|---|---|
| `/design-lab/supply` | DomainOverview: 5 headlines, lifecycle CategoryBars, PO ProportionBar by distributor, attention `inbound_open`, workflow PanelRows | New `/supply` hub | **COVERED** (structure) / PARTIAL (PO-by-distributor grain is linked/observed, not plan units) |
| `/design-lab/supply?lens=shipments` | Same page; lens ignored | Relocate workspace to `/supply/shipments` | **COVERED** (workspace relocated, not deleted) |
| `/design-lab/supply?lens=receipts` | Same page; lens ignored | `/admin/shipment-evidence` (nav `partial`) | **PARTIAL** — keep Partly built; wrap chrome; no per-shipment receipt view |
| `/design-lab/supply?lens=po` | Same page; lens ignored | `/admin/po-management` | **COVERED** (workspace wrapped, not deleted) |

## Production routes (AS-IS → migrate)

| Route | AS-IS | After N-0018 | Coverage |
|---|---|---|---|
| `/stock?lens=inbound` | `InboundShipmentsWorkspace` **without** StockChrome | Redirect → `/supply/shipments` | **COVERED** (relocate) |
| `/shipping` | middleware → `/stock?lens=inbound` | middleware → `/supply/shipments` (query preserved) | **COVERED** |
| `/admin/shipment-evidence` | PageHeader + evidence grid | `SupplyChrome` wrap; keep Partial marker | **PARTIAL** |
| `/admin/po-management` | PageHeader + `PoManagementView` | `SupplyChrome` wrap | **COVERED** |
| `/admin/imports?template=inbound_shipments` | Data & Stewardship import | stays Data (not a Supply lab leaf) | **out of Supply map** |
| Arrived as a lifecycle state | not in DB | not invented | **UNCOVERED** → BACKLOG-178 |
| Plan-unit PO % by distributor | lab fixture only | not computed | **UNCOVERED** → BACKLOG-179 |
| Stores master | N-0011 | untouched | **UNCOVERED** (already recorded) |

BACKLOG-079 (MasterDataGridShell on shipment-evidence) **does not fold in**: this unit wraps DomainHeader chrome, not that shell. BACKLOG-066 is not fired.

D-0002 mapping-queue disposition untouched.

---

## Browser 1280×800 (2026-09-07, Playwright)

Lab `/design-lab/supply` (fixture): Open 684 · Unreceived 1,714 · Received 312 · PO 79% · Backlog 16,050.

Production `/supply` (cip class iii): Open **1 964** · Unreceived **770** oldest 123d · Received this week **0** · PO **14%** (322/2308) · Backlog **118,024**. Meta `1 964 open · 770 past ETA`. Three disjoint lifecycle bars. Receipts workflow shows **Partly built**.

| Check | Result |
|---|---|
| `/supply` hub vs lab structure | **VERIFIED** |
| Workflows › Shipments real `<a href="/supply/shipments">` | **VERIFIED** (after PanelRow `href`; Chip no longer nested in `<p>`) |
| Open-shipments headline click | **VERIFIED** → `/supply/shipments` |
| Lens tab Shipments → Receipts & POD | **VERIFIED** → `/admin/shipment-evidence` |
| Lens tab → PO coverage | **VERIFIED** → `/admin/po-management` (workspace not deleted) |
| `/stock?lens=inbound` | **VERIFIED** → `/supply/shipments` |
| `/shipping` | **VERIFIED** → `/supply/shipments` |
| 390 named workflow | not required (DIRECTION §6) |

---

## Re-measure 2026-09-12 (implementer validate)

`current_database()=cip`. Same grains. Unreceived past ETA moved with the calendar: **873** / oldest **128d**. Open **1964**, POD this ISO week **0**, PO **322/2308**, pipeline units **118024**, lifecycle 1635 / 329 / 13065. Live `/supply` matched the API (Open 1 964 · Unreceived 873 · PO 14%). Do not write 873 back onto the 2026-09-07 row.


