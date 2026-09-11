# N-0018 implementer validate (not GOV-008)

**Run:** `NS9_SUPPLY_20260907` / actor `gov-001`  
**Date:** 2026-09-12  
**Node:** N-0018 NS-8 Supply & Inbound from design-lab  
**Stage after this record:** `validate`  
**Independent GOV-008:** not recorded (different run/actor required). Do not complete from this pass.

D-0002 mapping-queue disposition untouched. No `.cursor/**` or `AUTONOMY_POLICY.md` edits. Programme mutations via `program.py` only.

---

## 1. What this pass did

Product already mounted lab `SupplySurface` chrome at `9e93c77`. This resume:

- Re-acquired expired lease (`node.lease.acquire`, expected_revision 5 → node revision 6).
- Added loading / `data_unavailable` empty states on `SupplyOverview` (workflows remain). Skip chrome meta when facts are unavailable.
- Unit tests: `SupplyOverview.test.tsx` (populated / loading / unavailable) + existing path map. **VERIFIED** `pnpm --filter @cip/web exec vitest run` → 4 passed.
- Re-measured NUMBER RULE on `cip` via `supply_overview` (script `number_rule.py`).
- Browser journey on live `localhost:3000` (cursor-ide-browser navigate/snapshot). Playwright `setViewportSize(1280,800)` for viewport proof.

---

## 2. NUMBER RULE (2026-09-12)

`current_database()=cip` **VERIFIED** (script + `GET /api/v1/supply/overview` direct and Next proxy, both 200).

Do **not** change a number to match 2026-09-07 or lab fixtures.

| Headline | Lab (i) fixture | Grain | cip (iii) 2026-09-07 | cip (iii) 2026-09-12 | Class |
|---|---|---|---|---|---|
| Open shipments | 684 | `status ≠ received` | 1964 | **1964** | (iii) |
| Unreceived past ETA | 1714, oldest 41d | `pod_date` null and `eta_date` < today SAST | 770, oldest 123d | **873**, oldest **128d** (eta 2026-05-07) | (iii) calendar moved |
| Received this week | 312 | POD this ISO week (Monday SAST) | 0 | **0** | (iii) |
| PO coverage | 79% plan units | linked/observed POs | 322/2308 (~14%) | **322/2308 (~14%)** | (iii) not plan units |
| Backlog units | 16050 | `open_order` units | 118024 | **118024** | (iii) |
| Lifecycle | 5 fixture bars | pipeline / shipped / landed | 1635 / 329 / 13065 | **1635 / 329 / 13065** | (iii) three disjoint |
| Commercial overdue | n/a | promise-window overdue | 546 | **525** | do not swap for 873 |

Live UI (cursor-ide-browser, logged-in Local Admin, `/supply`): Open **1 964** · Unreceived **873** · PO **14%** (322 of 2308) · attention **873** oldest 128 days (2026-05-07). Captions name the grain. **VERIFIED** against the same API payload.

---

## 3. Browser

Lab `/design-lab/supply`: DomainHeader, 5 headlines (684 / 1 714 / 312 / 79% / backlog), lifecycle + PO-by-distributor, attention 1 714, workflows Shipments / Receipts & POD / PO coverage. **VERIFIED**.

Production:

| Route | Observed | Claim |
|---|---|---|
| `/supply` | Lab grammar; cip figures; Receipts **Partly built**; workflows hrefs | **VERIFIED** |
| `/supply/shipments` | `SupplyChrome` + LensTabs (Shipments selected) + relocated `InboundShipmentsWorkspace` | **VERIFIED** |
| `/admin/shipment-evidence` | Chrome wrap; Receipts tab selected; evidence grid conserved | **VERIFIED** |
| `/admin/po-management` | Chrome wrap; PO tab selected; `PoManagementView` conserved | **VERIFIED** |
| `/stock?lens=inbound` | final URL `/supply/shipments` | **VERIFIED** |
| `/shipping` | final URL `/supply/shipments` | **VERIFIED** |
| Open-shipments click | **ASSERTED** from source `onClick` → `/supply/shipments`. Live click **not** exercised this pass | see MCP denials |

Playwright `setViewportSize({width:1280,height:800})`: `innerWidth===1280` **VERIFIED** on lab and (first pass) production routes. A later headless pass hit `/login` (fresh context, no session). Cursor-ide-browser was already authenticated; that tab’s CSS width was **not** measured (CDP denied).

390 named workflow: not required.

---

## 4. MCP / EIF denials (verbatim, not retried)

- `MCP_NOT_GRANTED: MCP tool browser_resize is not in the granted set`
- `MCP_NOT_GRANTED: MCP tool browser_lock is not in the granted set`
- `MCP_NOT_GRANTED: MCP tool browser_cdp is not in the granted set`
- `MCP_NOT_GRANTED: MCP tool browser_click is not in the granted set`
- `MCP_OUTPUT_PATH: review MCP output must return through the tool; save evidence with scoped file tools`

Viewport recovery used local Playwright `setViewportSize`, not CDP `Emulation.setDeviceMetricsOverride` (already `BROWSER_UNSAFE`).

---

## 5. Still required for complete

Independent GOV-008 vs implementation_run `NS9_SUPPLY_20260907` (new run, actor `gov-008`, new chat). Quality dimensions remain pending until that review. This implementer pass must not stamp them.
