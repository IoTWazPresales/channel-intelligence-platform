# N-0025 implementer evidence — Start work + remaining obstruct findings

**Run:** `NS13_START_WORK_20260914` · **Actor:** `gov-001` · **2026-09-14**
**Do not complete.** Independent GOV-008 is a later session, different run and actor.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip`.

Discovery origin: 2026-09-13 audit on this branch ([Discovery audit findings](0b6aeac8-d969-4059-9fe2-f8488dfe4479)). Eleven obstruct findings. N-0024 closed the five wrong-destination ones. Six remain in this node.

---

## Enumeration (source, before product land)

Surfaces read: `CommandPalette.tsx`, `CapabilityDirectory.tsx`, `navConfig.ts`, hub `PlanningOverview` / `SupplyOverview` / `AdminOverview` Workflows + `HeadlineFigure` `onClick`, domain `*Chrome.tsx` `DomainHeader` actions, `ImportCenterOverview` `START_CARDS`, guided wizard cards on `/admin/imports`, `OverviewHub`, `FundingPointerLens`, Claims/Payments/Terms pages, `ChannelIntelligenceWorkspace`, `MastersLanding`, `DataChrome` LensTabs, `StewardQueueOverview`, `CporCaseWorkspace` settle, `CurrentLineupSection` empty copy.

Palette and directory are **finders of places** (leaf href + `what`). They do not start a verb. Hub Workflows repeat rail leaves. Header buttons are sparse.

### Five jobs — entry points and completable path

| Job | Existing work screen | Palette / directory / rail | Hub Workflows / figures | Header button | Import Center | Completes E2E? |
|---|---|---|---|---|---|---|
| Create a lineup | Unified lineup dialog `/admin/imports?unified=1` (also bulk backfill card, historical_lineup wizard). Cases then live at `/lineup/cases`. | Leaf **Lineup cases** → `/lineup/cases` (work existing cases, does not open the importer). Directory same. | Planning Workflows: Lineup cases → `/lineup/cases`. Figure: cases → `/lineup/cases`. No “create”. Planning chrome: **no actions**. | Data chrome **New import** → `/admin/imports` (generic, step 0). Funding **New promotion plan** is a different object. | Start card **Lineup (unified)** `?unified=1`. Wizard card **Lineup (unified import)**. | **VERIFIED** source: steward/admin can complete create via `?unified=1`. Planner role cannot see Import Center (`STEWARD_PLUS`). Planner can open cases only. Empty CurrentLineupSection tells the operator to use Import Center. |
| Import sell-through (CST) | Guided wizard `/admin/imports?template=customer_sell_through`. Per-job steward on that job. | Rail **Customer sell-through files** (Data) and **Sell-through** (Stock honesty landing `/channel-intelligence`, workspace at `/channel-intelligence/workspace`). | No Planning/Supply verb. Data headlines filter jobs, not start CST. | Data **New import** generic. Stock honesty **Go to Import Center** uses the CST template. | Start card **Retailer sell-through**. | **VERIFIED** source: steward/admin can complete import via the template deep-link. Stock leaf is an honesty pointer, not the importer. Workspace is a read grid, not propose/import. There is **no** “sell-through proposal” creator in product source — **ASSERTED** as CST import, not an unbuilt commercial proposal. |
| Import a shipping file | Guided wizard `/admin/imports?template=inbound_shipments`. | Rail **Shipments** → `/supply/shipments` (lifecycle grid, not importer). Receipts & POD partial → evidence steward. | Supply Workflows: Shipments / Receipts / PO — none is the importer. Figures open shipments or PO. Supply chrome: **no import action**. | Data **New import** generic. | Start card **Inbound shipments**. | **VERIFIED** source: steward/admin complete via template deep-link. A person on Supply has no header start. |
| Settle a case | `/commercial-planner/cpor-cases` Case book → `/commercial-planner/cpor-cases/[id]` `CporCaseWorkspace` + `SettlementConfirmDialog`. `SettlementContainer` is **not mounted** (CaseBookSurface test asserts absence). | Rail **Case book**. Claims `what` says apply is on the settlement desk. | No Funding hub Workflows panel (Funding is leaf tabs, not DomainOverview). | Funding **New promotion plan** `/promotions?new=1` (author, not settle). **Import claims / payments** → `/admin/imports` generic. | Claim evidence start card. | **VERIFIED** source: planner/admin can settle on the case desk after opening a case from the book. The named Claims/Payments leaves do not settle. |
| Work the steward queue | `/admin/mappings` legacy queue. Per-job stewarding stays on the import job (`StewardQueueOverview` copy). D-0002 disposition untouched. | Rail **Steward queue**. Palette/directory same. Attention failed_imports (N-0024) → `/admin/mappings`. | Data headlines, not a Workflows panel. | Data **New import** is the wrong door. | Start cards start imports, not the queue. | **PARTIAL (VERIFIED source):** legacy rows can be worked on `/admin/mappings`. Cross-job accept/reject is not this surface (D-0002). Per-job work requires `?import_job_id=` or the import job. This node does not invent that. |

### What each finder already provides

| Surface | Provides | Does not provide |
|---|---|---|
| Command palette (Ctrl/⌘K) | Ranked **places** from `shellNavGroups` (live+partial). | Verbs. “lineup” hits Lineup cases, not the unified importer. |
| Capability directory `/directory` | Catalog of every leaf + status. Open = domain home. | Start actions. |
| Hub Workflows | Rail leaves for Planning / Supply / Admin. | Create/import/settle verbs. |
| Headline figures | Counts → existing leaves (N-0024 destinations). | File upload or settle confirm. |
| Domain headers | Data: New import. Funding: Reports / Import claims-payments / New promotion plan. Overview, Planning, Supply: **none**. | Role-gated “I came to do X” on the arrival page. |
| Import Center start cards | Six typed starts including lineup, CST, inbound, claims. | Invisible unless the person already opened Data. |

**ASSERTED (discovery, still open before this node):** Attention answers “what is broken”. Rail answers “where does this live”. Nothing answers “I came here to do X”.

---

## Six remaining obstruct findings — disposition

N-0024 closed: cover-breach→Cover, failed-imports→steward queue, inbound-open→`/supply/shipments`, Lineup cases three hrefs, Users & roles→list.

| Finding | Close in this node? |
|---|---|
| Claims / Payments / Terms empty pointer defaults | **Yes.** Payments/Terms: drop `?import=1` / `?edit=1` gates so the named leaf **is** the wizard/editor. Claims: no second importer — in-page rows route to Import Center `cpor_claim_evidence` and Case book. |
| Data in-page tabs hide Products, Customers, duplicates, CST, gaps | **Yes, without adding tabs.** Keep four LensTabs. List rail-only destinations in-page on Data chrome. Crumb the named leaf on child pages. |
| Sell-through numeric ids | **Yes.** Name autocomplete + name columns. Filter still `customer_id` / `product_id` after pick. Display names are read-model joins, not stored facts. |
| Empty Business dashboard prime + attention clips at 312px | **Yes.** Start work occupies prime. Empty dashboard is a compact link, not the left column. Attention stays exceptions-only and wider than 312px. |
| Stores: Master data card, no grid | **Record, not close.** No production grid exists. Do not invent one. |
| SKU assumptions / pin-as-widget / JSON drawer / grid chrome | **Record.** SKU assumptions stay on commercial planner (Terms already links). Pin-as-widget UNCOVERED (CURRENT). Drawer JSON not the named finding. Grid chrome out of scope. |

---

## Placement (from the evidence)

One surface: **Start work** on Overview `/brief` (where a person arrives). Not a new rail domain, not stuffed into Attention, not a per-domain IA object.

Verbs (role-gated, existing hrefs only):

| Verb | href | Roles |
|---|---|---|
| Create a lineup | `/admin/imports?unified=1` | admin, steward |
| Open lineup cases | `/lineup/cases` | admin, planner |
| Import sell-through | `/admin/imports?template=customer_sell_through` | admin, steward |
| Import a shipping file | `/admin/imports?template=inbound_shipments` | admin, steward |
| Settle a case | `/commercial-planner/cpor-cases` | admin, planner |
| Work the steward queue | `/admin/mappings` | admin, steward |

Planner cannot complete create-lineup (Import Center is `STEWARD_PLUS`) — they get Open lineup cases. Viewer gets no verbs (directory/palette remain).

---

## Implementation notes (filled after land)

One Start work panel on Overview `/brief` (`data-testid="start-work"`). Verbs from `apps/web/src/features/overview/startWork.ts`. Attention stays blotter-only. Desktop grid `minmax(0, 1.1fr) minmax(380px, 0.9fr)` = Start work | Attention. Empty Business dashboard is a compact row **below** (tenant dashboard named **test**, 0 widgets). Lab `OverviewSurface.tsx` **312px left unchanged** (lab fixture, not production OverviewHub).

Payments: dropped `?import=1` gate; default is `PaymentEvidenceImportWizard`. Residual same-URL “Back to Payments lens” chrome remains; it is not the old empty pointer. Terms: dropped `?edit=1`; default is `CustomerTermsEditor` (no “Back to Terms lens”). Claims: two PanelRows — Import Center `cpor_claim_evidence` and Case book. No second importer. `SettlementContainer` not mounted.

Data: four LensTabs kept. `dataAlsoHere.ts` strip (`data-testid="data-also-here"`). Child crumb uses `matchNavLeaf` (Products named). Stores still UNCOVERED. SKU assumptions stay on commercial planner. Pin-as-widget UNCOVERED.

Sell-through: `EntitySearchAutocomplete` Customer/Product; grid names via `cst_read_model._attach_display_names` (display-only dim joins). Filter still `customer_id` / `product_id`. Not a stored-column mapping change.

Vitest: `startWork.test.ts` 5, `OverviewHub.test.tsx` 1, `DataChrome.test.ts` 2 — 8 passed. Pytest: `apps/api/tests/test_channel_intelligence_u46.py` — 7 passed (names `None` under MagicMock execute). No `cip` writes. No `browser_cdp`.

## Click verification

Playwright MCP against `http://localhost:3000`, Local Admin, 2026-09-14. Click-result URLs can lag one navigation; **final URL taken from a later snapshot or `location.href`**.

| Surface | Action | Expected | Observed | Status |
|---|---|---|---|---|
| Overview 1280×800 | Load `/brief` | Start work prime; six verb hrefs; Attention exceptions-only | Start work left (525×354 at x=273); six links with correct hrefs; Needs attention still 3 urgent (failed imports / cover / inbound) | **VERIFIED** |
| Overview 1280 | Attention column width | Wider than 312px; cover text readable | Attention 431px; cover copy “102 pairs under 4 weeks…” in a11y tree | **VERIFIED** |
| Overview 1280 | Empty dashboard | Compact below, not prime | dashboard-zone y=770 h=72 w=971; “test · 0 widgets”; Open Business dashboard | **VERIFIED** |
| Start work | Create a lineup | `/admin/imports?unified=1` + unified dialog | Final URL `?unified=1`; dialog “Unified lineup import (multi-file)” | **VERIFIED** |
| Start work | Import a shipping file | `?template=inbound_shipments` wizard | Final `location.href` that template; “Selected type: Shipment / order evidence (inbound_shipments)” | **VERIFIED** |
| Start work | Import sell-through | CST template wizard | href on Start work **VERIFIED**; same wizard as shipping — click **SKIPPED** | href **VERIFIED**; click **SKIPPED** |
| Start work | Settle a case / steward queue | Case book / `/admin/mappings` | hrefs on Start work **VERIFIED**; clicks **SKIPPED** (N-0024 already opened mappings) | href **VERIFIED**; click **SKIPPED** |
| Payments | Open `/commercial-planner/cpor-cases/payment-evidence-import` | Wizard, not pointer | Choose workbook + Upload & validate; Payments tab selected | **VERIFIED** |
| Terms | Open `/admin/customer-commercial-terms` | Editor, not pointer | Filter + Add terms + terms grid; Open SKU assumptions → `/commercial-planner`; no pointer | **VERIFIED** |
| Claims | Open `/commercial-planner/cpor-cases/claims` | Two rows | Import claim evidence + Open Case book to settle | **VERIFIED** |
| Claims | Click import row | Import Center `cpor_claim_evidence` | URL that template; “Selected type: CPOR claim evidence” | **VERIFIED** |
| Data | Also in this area | Products, Customers, CST, gaps, duplicates | Strip on Import Center and Products; CST files + gaps + both duplicate leaves + CST steward | **VERIFIED** |
| Data | Products crumb | Names Products | Crumb Data & Stewardship / Products | **VERIFIED** |
| Sell-through | `/channel-intelligence/workspace` | Names not numeric ids | Combobox Customer / Product; grid “Hifi (CUST-000005)” and sales-model names | **VERIFIED** |
| Overview 390×844 | Start work reachable | Visible | Heading + six verbs **before** Needs attention; bottom nav present | **VERIFIED** |

Keyboard/axe: **UNVERIFIED**. Planner/viewer role live: **UNVERIFIED** (admin session only; unit tests cover role gating). Lab 312px OverviewSurface: **ASSERTED** source (unchanged). Stores grid / pin-as-widget: **UNCOVERED** (not invented).

## Preservation

D-0010 Option A kept. D-0002 / N-0006 / N-0013 / BACKLOG-181 untouched. Movement/Execution workspaces not unwound. No column-picker work. Attention not used as a start menu. Independent GOV-008 not recorded. Do not complete.
