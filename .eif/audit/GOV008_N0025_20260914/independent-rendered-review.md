# N-0025 independent GOV-008 review

**Run:** `GOV008_N0025_20260914`
**Actor:** `gov-008` (this session; not the implementer)
**Date:** 2026-09-14
**Implementation run (anchored):** `NS13_START_WORK_20260914` / `gov-001`
**Reviewer HEAD at start:** `0aa90650a4db7f11c4cd9365d4a04dd682535c14` on `feat/ns-2-brief-nav-collapse`
**Product pin:** `04695c15bee716070ea88df95dd1db400aaa59eb`
**Programme snapshot at reclaim:** 614; node revision 21 → 22
**Out of scope:** D-0002, N-0006, N-0013, BACKLOG-181, Movement/Execution relocated workspaces, column-picker / grid chrome, remediating N-0025 in this session.

This is **implementation-verification**. Implementer evidence is DATA. Enumeration below was produced from product source and Playwright **before** reading `.eif/audit/NS13_START_WORK_20260914/implementer-evidence.md`. `browser_cdp` was not invoked. No writes to `cip` (CST file not uploaded; settle confirm not pressed; no planner user created).

---

## Verdict

**VERIFIED_WITH_LIMITATIONS.** Node **not completed**.

The charter is met on the product that shipped: one Start work surface on Overview, verbs route into screens that already existed, remaining obstruct findings closed or recorded, D-0010 Option A kept, no parallel creator. Independent clicks closed the three implementer SKIPPED rows for CST, settle, and steward queue. Limitations below are why this review does not `complete()`.

**Limitations (blocking complete):**

1. **Steward queue verb cannot complete the live work.** Clicking Start work → Work the steward queue landed on `/admin/mappings`. Domain header: `0 legacy queue rows`. Caption: `2814 per-job candidates still need_review; cross-job queue is D-0002`. Empty state: “Mapping queue is empty”. The 2814 candidates are not on this grid without `?import_job_id=`. Charter forbids touching D-0002. AC1 required recording where the job breaks — it breaks here. Completing the node would claim the named job is reachable as work; it is reachable as an empty leaf.
2. **Planner role not live-tested.** Tenant Users table has only `admin@local` and `viewer@local`. Creating a planner would write `cip`. Unit tests in `startWork.test.ts` assert planner sees `open-lineup` + `settle-case` only. That remains **ASSERTED**, not live **VERIFIED**.
3. **Payments residual same-URL chrome.** Named Payments leaf **is** the wizard (AC4 **VERIFIED**). “Back to Payments lens” still hrefs `/commercial-planner/cpor-cases/payment-evidence-import`. Click stayed on the same URL. Misleading leftover, not a restored empty pointer. Not remediated here.

**Limitations (non-blocking coverage):**

- CST apply and settle confirm not executed (cip write forbidden). Paths were clicked through to Choose file / Confirm settlement dialog.
- Keyboard/axe **UNVERIFIED**.
- Clean-week (zero attention signals) not rendered; Start work is not gated on signal count in source (**ASSERTED**).
- No CLI second-model consult.

---

## Independence

Fresh run `GOV008_N0025_20260914` / actor `gov-008`, distinct from `NS13_START_WORK_20260914` / `gov-001`. Own Playwright MCP. Own source enumeration before implementer evidence. Not a second-LLM consult.

---

## Session start / denials (verbatim)

First git call blocked fail-closed. Retry:

```
SESSION_CLOSURE_REQUIRED: Remote closure proof pending. Run from the project root, subject to shell policy: python -B .cursor/hooks/eif_guard.py --verify-closure 3f18147295fd1db7c98b757f0d8dfe1bfa50fc36f31814534c0f9cf3c131f6db cbf7353d95c24e819f602de12ae8fdbd. Reads and policy-permitted recovery remain available; do not claim closure yet.
```

Ran that command exactly:

```
{"ok": true, "reason_code": "SESSION_CLOSURE_OK", "decision_kind": "policy", "message": "ledger_commit=47602ff5218bd5d640cd5146083c0ed756e0c462; verified_remote_head=0aa90650a4db7f11c4cd9365d4a04dd682535c14"}
```

Other skips: Playwright screenshot with custom path → `MCP_OUTPUT_PATH` (retried without filename); intermittent eif_guard fail-closed on find/wait (retried once then skipped that call). `browser_cdp` not invoked.

---

## Independent enumeration (source, before implementer evidence)

Surfaces read: `startWork.ts`, `StartWorkPanel.tsx`, `OverviewHub.tsx`, `CommandPalette.tsx`, `CapabilityDirectory.tsx`, `navConfig.ts`, `PlanningOverview.tsx` + `planningPaths.ts`, `ImportCenterOverview.tsx` `START_CARDS`, `apps/web/src/app/(app)/admin/imports/page.tsx` (`?unified=1` / `?template=`), `CaseBookSurface.tsx`, `CporCaseWorkspace.tsx`, `admin/mappings/page.tsx`, Payments / Terms / Claims pages, `DataChrome.tsx` / `dataAlsoHere.ts`, `ChannelIntelligenceWorkspace.tsx`, `cst_read_model.py`.

Palette and directory are **finders of places** (`shellNavGroups`). Hub Workflows repeat rail leaves. They do not mint Start work verbs.

### Five jobs

| Job | Existing work screen | Palette / directory / rail | Hub Workflows / figures | Header | Import Center start cards | Completes E2E from Start work? |
|---|---|---|---|---|---|---|
| Create a lineup | Unified dialog `/admin/imports?unified=1` | Rail **Lineup cases** → `/lineup/cases` (existing cases, not importer). Palette “lineup” hits cases. | Planning Workflows + cases figure → `/lineup/cases`. No create. | Data **New import** generic. | **Lineup (unified)** | **VERIFIED** click: dialog “Unified lineup import (multi-file)” + Choose files. Existing screen. File not uploaded. |
| Import sell-through | Wizard `?template=customer_sell_through` | Rail **Customer sell-through files**. Stock **Sell-through** is honesty + workspace, not importer. | No Planning/Supply CST start. | Data New import generic. | **Retailer sell-through** | **VERIFIED** click: type preselected, provider Incredible Connection CST P4, Next through to **Choose file**. Apply not run. |
| Import a shipping file | Wizard `?template=inbound_shipments` | Rail **Shipments** is lifecycle, not importer. | Supply Workflows are not the importer. | Data New import generic. | **Inbound shipments** | **VERIFIED** click: “Selected type: Shipment / order evidence (inbound_shipments)”. |
| Settle a case | Case book `/commercial-planner/cpor-cases` → `/commercial-planner/cpor-cases/{id}` `CporCaseWorkspace` + `SettlementConfirmDialog` | Rail **Case book**. | Funding has no DomainOverview Workflows panel. | Funding **New promotion plan** is authoring, not settle. | Claim evidence card is import, not settle. | **VERIFIED** click: Start work → book → Ended filter → C24446638 (`case=46`) → Settlement workspace → **Settle** → dialog “Confirm settlement · R 1,517,439.79”. Confirm not pressed. Existing desk. `SettlementContainer` not mounted (**ASSERTED** source; CaseBookSurface test). |
| Work the steward queue | `/admin/mappings` legacy `EntityMappingQueue` | Rail **Steward queue**. Attention “failed imports” also → `/admin/mappings`. | Data headlines filter jobs. | New import is the wrong door. | Start cards start imports. | **VERIFIED** click + **break:** empty legacy grid; 2814 `needs_review` candidates are per-job. D-0002 untouched. |

### Role gating (source)

`START_VERBS` in `startWork.ts`: create/CST/shipping/steward = `admin|steward`; open-lineup/settle = `admin|planner`. Viewer filtered to `[]`. Tests match.

Live: **viewer@local** / `changeme1` on `/brief` — Start work subtitle “No start actions for this role”; body “Nothing this role can start from Overview.” Footer **Viewer**. **VERIFIED**. Planner: no tenant user. **ASSERTED** tests only.

### Remaining obstruct findings

| Finding | Independent result |
|---|---|
| Payments/Terms empty pointer | Payments URL has no `?import=1`. Choose workbook + Upload & validate on the leaf. Terms `/admin/customer-commercial-terms` has Add terms + grid, no `?edit=1`. **VERIFIED**. Residual Payments back-link judged above. |
| Claims second importer | Claims leaf is two PanelRows: Import Center `cpor_claim_evidence` and Case book. Click import → “Selected type: CPOR claim evidence”. **VERIFIED**. |
| Data tabs hide Products etc. | Four LensTabs kept. Also-here strip: CST files, Products, gaps, Customers, duplicates, CST steward. Click Products → `/admin/products` crumb **Data & Stewardship / Products**. **VERIFIED**. |
| Sell-through numeric ids | `/channel-intelligence/workspace`: combobox Customer/Product; grid `Hifi (CUST-000005)` + sales-model names; options `CUST-000005 — Hifi`. Filter remains id after pick (source). **VERIFIED**. |
| Empty dashboard prime + 312px clip | 1280: Start work left `526×510` at x=272; Attention **431px** at x=814; dashboard compact below y=711. 390: Start work first (y=201) above Attention (y=650). **VERIFIED**. Lab `OverviewSurface` 312px **ASSERTED** unused by production OverviewHub. |
| Stores grid / pin-as-widget / SKU editor / SettlementContainer | Not invented in `04695c1`. **UNCOVERED** recorded. |

No parallel workflows: every clicked verb opened a screen that already existed (Import Center wizard/dialog, Case book + case desk, mappings leaf).

---

## Click table (this session)

| Surface | Action | Observed | Status |
|---|---|---|---|
| Overview 1280 | Load `/brief` as admin | Start work six verbs; Attention 3 urgent, 431px; dashboard below | **VERIFIED** |
| Start work | Click Import sell-through | Wizard CST; Choose file after provider + Next | **VERIFIED** |
| Start work | Click Settle a case | Case book → case 46 desk → Settle confirm dialog | **VERIFIED** |
| Start work | Click Work the steward queue | `/admin/mappings` empty; 2814 per-job | **VERIFIED** arrive; **cannot complete** |
| Start work | Click Create a lineup | Unified multi-file dialog | **VERIFIED** |
| Start work | Click Import a shipping file | inbound_shipments selected | **VERIFIED** |
| Payments | Open leaf + click Back to Payments lens | Wizard default; back-link same URL no-op | **VERIFIED** residual |
| Terms | Open leaf | Add terms; no `?edit=1` | **VERIFIED** |
| Claims | Click Import claim evidence | `cpor_claim_evidence` wizard | **VERIFIED** |
| Data | Also-here Products | crumb Products | **VERIFIED** |
| Sell-through | Workspace names | Hifi names, not raw ids | **VERIFIED** |
| Overview 390 | Start work | Visible above Attention; bottom nav | **VERIFIED** |
| Overview | Login viewer@local | No start verbs | **VERIFIED** |
| Overview | Login planner | No planner user; not created | **UNVERIFIED** live |

---

## Comparison with implementer evidence (read after enumeration)

Implementer enumeration of finders vs verbs matches source. Implementer **SKIPPED** CST / settle / steward clicks; this run clicked them. Implementer already labelled steward as PARTIAL and planner/viewer live as UNVERIFIED. Residual Payments back-link was already recorded by the implementer. No contradiction that would reject the implementation; the steward complete-the-job gap is why this review withholds `complete()`.

---

## Preservation

D-0010 Option A: four Data LensTabs still present. D-0002 copy still on mappings. N-0006 / N-0013 / BACKLOG-181 not reopened. Rail expansion and tabs remain. Attention still blotter-only (failed imports / cover / inbound). Movement/Execution not unwound.
