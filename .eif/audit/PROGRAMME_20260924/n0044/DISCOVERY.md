# N-0044 discovery: D-c + rest of 2.7

Discovery seat, read-only. Lenses: product-manager, analytics-bi-specialist, frontend-engineer, product-interaction-designer. Date 2026-09-24. Branch `feat/ns-2-brief-nav-collapse`.

Operator decision D-c (Warren, 2026-09-23), verbatim: "CporCaseWorkspace retires once the desk absorbs the BACKLOG-202 pieces. SettlementPortfolioRead and CporPortfolioIntelligencePanel: check overlap with existing surfaces. If they show intelligence nothing else shows, mount them under Promotions & Funding per the lab; if they duplicate existing surfaces, delete them. Report which, and why."

## Evidence method and limits

- All claims come from reading code (paths cited below), plus read-only GET calls to the live API from a browser tab at http://127.0.0.1:3000 on 2026-09-24. Nothing was clicked or written.
- **UNABLE_TO_RENDER, desk:** `/commercial-planner/cpor-cases/46` and `/311` stayed on "Loading case…" in a background MCP tab for more than 30 s, and no `/api/` resource entries appeared. Direct `fetch` of the same endpoints from that page returned 200 in about 300 ms, so the API is healthy. The likely cause is react-query/visibility in a hidden tab, not a desk defect; this was not proven. The desk-side claims below are therefore **code-verified, with live data confirmed through the API only**.
- Live API facts used below:
  - Case 46 `C24446638`: `status=ended`, `allowed_next=[cancelled, settled]`, `needs_reapproval=true`, `fx_mode=booked`, ROE 19.14, `ttl_support_zar` 1,517,439.79, `ttl_support_usd` 79,361.28, `evidence_basis=source_attested`, 0 claim rows. Comparable-cases: 382 candidates, 8 items, 822 ms.
  - Case 311 `C26760971`: `status=settled`, `allowed_next=[]`, ROE 16.50, ZAR 1,616,231.52, USD 97,953.43.
  - Portfolio: 304 cases, 621 lines. `support_usd` 1,617,054, `support_zar` 28,862,698. Delivery rate 61.8% (29,970 / 48,463). Support per unit sold $53.96 (R963). Claim-evidenced-only is 0 cases, so its delivery rate is null. Incremental unit cost: 8 ok, 192 flagged, avg $70.62. Evidence mix: 0 claim, 230 attested, 74 none.
  - Settlement book: `book_total` R4,404,917, USD booked 242,118, 74 open cases, 74 booked, 0 unbooked.

## 1. BACKLOG-202 pieces: CporCaseWorkspace vs the desk

The route `/commercial-planner/cpor-cases/[id]` renders `SettlementDeskLive` inside `FundingChrome hideDomainHeader` (`app/(app)/commercial-planner/cpor-cases/[id]/page.tsx`). `CporCaseWorkspace` has one referent, `page.fxReadiness.test.tsx:8,142`. (Paths are relative to `apps/web/src/` unless noted.)

### 1a. FX anchor

- **Workspace:** `features/cpor/CporCaseWorkspace.tsx:540-552` mounts `CporFxAnchorPanel` (`features/cpor/CporFxAnchorPanel.tsx`). It shows:
  - the approved case support (`ttl_support_zar`) in large type;
  - the booked USD basis line (`buildFxMoneyDisplay`) with booked-by and booked-at;
  - an "FX undeclared" warning;
  - the proposed rate, its source and time.
- **API:** `GET /api/v1/cpor/cases/{id}`. The fields are already on the desk's detail query.
- **Desk equivalent: PARTIAL.**
  - Every desk money figure is a `DualMoney` using `view.roeSnapshot` (`SettlementDesk.tsx:86-94, 307-340`).
  - The FX basis line shows only when settle is blocked (`SettlementDesk.tsx:286-291`).
  - The DomainHeader meta shows only the currency (`SettlementDesk.tsx:219`).
  - **Missing:** the approved plan total (`ttl_support_zar/usd`; the desk shows CIP, customer and agreed amounts, but not what was approved), the non-blocked basis line, booked by/at, and the proposed rate/source.
  - `SettlementDeskCase` (`mapSettlementDeskView.ts:13-28`) does not type `ttl_support_zar`, `ttl_support_usd`, `fx_proposed_*` or `fx_declared_*`, even though the API returns them.
- **Smallest port, using existing desk primitives:**
  1. Extend `SettlementDeskCase` and `SettlementDeskView` with `approvedAmount` (from `ttl_support_zar`), `approvedUsd`, `fxBookedBy`, `fxBookedAt`, `fxProposedRate` and `fxProposedSource`.
  2. Add a sixth `HeadlineFigure` "Approved support" as the first item in the `HeadlineStrip` (`SettlementDesk.tsx:307`, columns 5→6). Render it with `moneyDual`, captioned `booked ZAR x/USD · by · at`, or "proposed x · not booked".
  3. Append `view.fxBasisLine` to the DomainHeader `meta` whenever FX is not blocked.
  - Do not mount `CporFxAnchorPanel` itself: its 34px bespoke hero duplicates the HeadlineStrip job. Once the workspace goes, `CporFxAnchorPanel` has no referent and is deleted. `buildFxMoneyDisplay` stays, because `DualMoney` uses it.

### 1b. Settle readiness row

- **Workspace:** `CporCaseWorkspace.tsx:472-486` renders `CporSettleReadinessRow` (chips from `buildSettleReadinessChips`: FX declared/mode, open assumptions, claim evidence, evidence basis) plus the `fx_basis_line` caption. It renders a second copy in the settlement tab at `:686-688`.
- **API:** `settle_readiness` on `GET /cpor/cases/{id}` and on `GET /cpor/cases/{id}/settlement`.
- **Desk equivalent: PARTIAL.**
  - The readiness chips appear only inside the settle confirm modal (`SettlementConfirmDialog.tsx:93`).
  - On the page itself, the desk only uses readiness negatively: the `fxSettleAllowed` alert and the CTA gating (`SettlementDesk.tsx:98-99, 286`).
  - Before opening the dialog, Ken cannot see why settle is or is not available. For example, case 46 shows `claim_evidence_count 0` and `evidence_basis source_attested`.
- **Smallest port:** put the chip row at the top of the existing "Next action" `Panel` (`SettlementDesk.tsx:412-450`). Pass `settle_readiness` through the view.
  - Either reuse `CporSettleReadinessRow` (it is already a desk dependency through the confirm dialog), or map `buildSettleReadinessChips` onto workbench-ui `StatusChip`s.
  - Prefer `StatusChip`: `CporSettleReadinessRow` hard-codes hex tone colours (`CporSettleReadinessRow.tsx:10-26`) instead of theme tokens. That is a design-system finding either way.

### 1c. Comparable cases

- **Workspace:** `CporCaseWorkspace.tsx:553` mounts `CporComparableCasesPanel` (`app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel.tsx`).
- **API:** `GET /api/v1/cpor/intelligence/comparable-cases?case_id=&limit=8` (A2-05). Live: 822 ms.
- **Desk equivalent: NONE on the desk.** The panel is already mounted elsewhere, on the planner: `PlanWorkspace.tsx:484-486`, inside `Panel "Comparable cases — same customer & family"`.
- **Smallest port:** add a sixth tab `{ key: 'comparables', label: 'Comparable cases' }` to `SettlementCaseTabs.tsx:14-20,77-81`. It mounts lazily, so the 800 ms query fires only on demand. This keeps the desk's "next action without opening tabs" headline clean.
  - Alternative: a `Panel` under the grid, matching `PlanWorkspace`. That puts an eager 800 ms query on every desk load.

### 1d. Transition buttons

- **Workspace:**
  - The action row covers propose, approve, reject, resend, activate, end, settle and cancel (`CporCaseWorkspace.tsx:142-151, 390-405, 554-581`). The list is filtered by `allowed_next`, and settle is hidden when `fx_settle_allowed === false`.
  - An approve-and-book-FX dialog sends `fx_rate` and `confirm_over_budget_reapproval` (`:745-787`).
  - A reject dialog requires a comment (`:789-812`).
  - A needs-reapproval chip and banner sit at `:431-433, 527-532`.
- **API:** `POST /api/v1/cpor/cases/{id}/transition`.
- **Desk equivalent: PARTIAL.** The desk wires only `settle` (`SettlementDeskLive.tsx:56-58`), plus supersede and restore (`:67-74`). There is no cancel and no end.
  - Live case 46 is `ended` with `allowed_next=[cancelled, settled]`. The desk exposes settle but not cancel, and does not show `needs_reapproval=true`.
- **Where the other transitions already exist:**
  - `PlanWorkspace.tsx:121-131, 283-330` covers all `allowed_next` actions, with a reject comment dialog at `:590`.
  - `CaseBookSurface.tsx:296-308, 806-819` covers approve and reject from the case drawer.
  - **Neither sends `fx_rate` or `confirm_over_budget_reapproval`.** A grep over `features/promotions-funding/*` for both field names returns no hits. The approve-and-book-FX dialog and the over-budget reapproval exist **only** in `CporCaseWorkspace`.
  - **Finding:** `PlanWorkspace` shows `settle` whenever it is in `allowed_next`, with no `fx_settle_allowed` gate and no `SettlementConfirmDialog` (`PlanWorkspace.tsx:283-286`). That is a second settle path that bypasses the desk's readiness and confirm step.
- **Smallest port (interaction design):**
  - The desk owns the post-live half: end, cancel and settle.
    - Add the actions `allowed_next ∩ {ended, cancelled}` to the DomainHeader `actions` as outlined buttons next to "Supersede…" (`SettlementDesk.tsx:220-254`).
    - Cancel needs a confirm dialog.
    - Add a `StatusChip` "Needs reapproval (over budget)" when `needs_reapproval` is true.
  - Pre-approval actions (propose, approve, reject, resend, activate) belong to the planner. The desk links to it with "Open in planner" (`/promotions?plan={id}`).
  - **Before the workspace is deleted,** the approve-and-book-FX dialog (`fx_rate`) and `confirm_over_budget_reapproval` must move to `PlanWorkspace`'s approve button. Otherwise booking a rate at approval and over-budget reapproval become unreachable from the UI.

### 1e. Other CporCaseWorkspace capabilities not on the desk (whole component read)

| # | Capability | Workspace file:line | API | Elsewhere? |
|---|---|---|---|---|
| 1 | Exclude-from-intelligence switch (comparables, norms, book totals) | 283-292, 435-453 | `POST /cpor/cases/{id}/intelligence-exclude` | **Nowhere.** Grep of `intelligence-exclude` in web src hits only the workspace. It would be lost. |
| 2 | FX mode toggle booked/floating (draft or rejected only) | 267-273, 487-502 | `PATCH /cpor/cases/{id}` `{fx_mode}` | Only at create (`PromotionPlannerSurface.tsx:659`). It would be lost for existing drafts. |
| 3 | Proposed ZAR/USD edit and save | 275-281, 503-525 | `PATCH /cpor/cases/{id}` `{fx_proposed_rate}` | Only at create (`PromotionPlannerSurface.tsx:660`). It would be lost. |
| 4 | Approve-and-book dialog (`fx_rate`) and over-budget reapproval | 745-787 | `POST …/transition` | **Nowhere** (see 1d). |
| 5 | Re-rollup from claims | 257-265, 650-658 | `POST /cpor/cases/{id}/settlement/rollup` | Nowhere in web src outside the workspace. |
| 6 | Include out-of-window rows toggle on claim upload | 640-649 | form field `include_out_of_window` | The desk hard-codes `'false'` (`SettlementDeskLive.tsx:47`). |
| 7 | Settlement diagnostics: out-of-window count, unresolved products and tokens, CST divergence chip | 689-717 | `GET …/settlement` (`out_of_window_claim_rows`, `unresolved_products`, `cst_reconciliation`) | The desk ignores these fields (`mapSettlementDeskView.ts`). SettlementConfirmDialog gets no unresolved count from the desk (`SettlementDeskLive.tsx:157-169`, contrast workspace `:742`). |
| 8 | Claim-import result summary (rows upserted, lines updated, unresolved, out-of-window) | 678-685 | import response | The desk shows errors only. |
| 9 | Header chips: `workflow_status`, `export_version`, `evidence_basis`, first 6 flags, PM `last_comment` | 427-471, 533-539 | detail | Evidence basis and flags are not on the desk. Export version is visible in the Exports tab. |
| 10 | Lines grid (SRP, margin, cost/source, dealer px, support/u, ttl local, flags) and Add line dialog | 294-344, 598-605, 814-861 | `POST /cpor/cases/{id}/lines`, `GET /products` | Covered by the planner: `PlanWorkspace` has lines, add line (`:136`) and line PATCH (`:113`). |
| 11 | Settlement grid with Ttl result local/USD per line | 346-383, 718-723 | `GET …/settlement` | Desk grid has quantities only, no money columns; per-line support/u is in the drawer only. |
| 12 | USD pivot, Events, Exports, Promo load, Payments/recon tabs | 588-611, 727-728 | various | **Already ported** in `SettlementCaseTabs.tsx` (N-0032). |

Items 1 to 8 are what the desk has to take (or the planner, for 2 to 4) before `CporCaseWorkspace` can go. Items 1 and 5 to 8 sit on the settlement side. Put 1 (exclude switch) and 5 and 6 (re-rollup, out-of-window toggle) behind a desk overflow or a "Claims" tab. Put 7 and 8 as `StatusChip`s in the Evidence section of the Next-action Panel (`SettlementDesk.tsx:440-449`). Items 2 to 4 belong on `PlanWorkspace`. Item 11 is optional: add ttl result local via `DualMoney` as a desk grid column.

## 2. The two portfolio panels

### 2a. What each shows

Both call `GET /api/v1/cpor/intelligence/portfolio`, which is `build_portfolio_intelligence` (`apps/api/app/services/cpor/portfolio_intelligence.py:36`).
- Scope: non-superseded cases that are not intelligence-excluded (`where_commercial_intelligence`), including settled.
- Lines: voided lines and lines with estimate ≤ 0 are excluded.
- `support_usd` = Σ `_line_ttl_support_usd` (`pivot.py:30-38`): the stored `ttl_support_usd`, else `support_usd × estimate_qty`. **None becomes 0** (`portfolio_intelligence.py:133-136`).
- `support_zar` = Σ `ttl_support`, whatever the case currency (None becomes 0).
- Delivery rate = Σ result / Σ estimate. Support per unit = Σ support / Σ result.

| Panel | Figure | Source |
|---|---|---|
| **SettlementPortfolioRead** (`features/settlement/SettlementPortfolioRead.tsx`, 114 lines) | Header: cases / lines, evidence mix | portfolio |
| | Support spend USD (ZAR secondary) | `totals.support_usd/zar` |
| | Delivery rate, result / est | `totals.delivery_rate` |
| | Support per unit sold USD / ZAR | `totals.support_per_unit_sold_*` |
| | Cost per incremental unit, ok / flagged | `incremental_unit_cost` (BACKLOG-089) |
| **CporPortfolioIntelligencePanel** (`app/(app)/commercial-planner/cpor-cases/CporPortfolioIntelligencePanel.tsx`, 315 lines) | The same four tiles and header | portfolio |
| | Claim-evidenced-only delivery rate and case count | `claim_evidenced_only` |
| | Top BU (USD, ZAR), top promo type, cases / lines | `by_bu[0]`, `by_promotion_type[0]` (by_customer is fetched but not shown) |
| | Support bias (A1-09): planned, actual, bias %, missing-SKU alert | `GET /cpor/intelligence/support-bias?limit_cases=100` |
| | Support norms, trailing 4Q: top 5 customers with avg USD/ZAR, % of SRP, quarters present, window, anchor, source, attested-unmatched count | `GET /cpor/intelligence/norms` (A2-04) |

`SettlementPortfolioRead` is a strict subset of `CporPortfolioIntelligencePanel`: same endpoint, same query key `['cpor','intelligence','portfolio']`, four of the same tiles. Its only mount is `SettlementBookRead.tsx:56`. `SettlementBookRead` is mounted only by `SettlementContainer.tsx:59`, and **nothing imports `SettlementContainer`**. Grep across web src finds no importer. The whole pre-Composition-A queue+pane settlement layout is orphaned: `SettlementContainer`, `SettlementBookRead`, `SettlementCasePane`, `SettlementRegimeStrip`, `SettlementScopeBar`, `SettlementShapeBar`, `SettlementTaskCrumb`, `useSettlementBook`, `settlementViews`. `CporPortfolioIntelligencePanel` has no importer at all.

### 2b. Mounted Promotions & Funding surfaces (`features/shell/navConfig.ts:204-257`, `FundingChrome.tsx:24-32`)

| Lens / route | What it shows (portfolio-relevant) |
|---|---|
| FundingChrome header, every lens (`FundingChrome.tsx:80-117`) | Meta line: plans in planning, live, ended, book total (compact), **"delivery rate x% (mixed evidence)"** from the same portfolio endpoint |
| Promotion planner `/promotions` (`PromotionPlannerSurface.tsx`) | HeadlineStrip: drafts to finish, ended, settled book, **Planned reserve** and **Actual support** from `support-bias` (no `limit_cases`) |
| Plan workspace `/promotions?plan=id` (`PlanWorkspace.tsx`) | Per-case totals, budget after plan, per-case support-bias planned/drawn, **Comparable cases panel** |
| Case book `/commercial-planner/cpor-cases` (`CaseBookSurface.tsx:436-640`) | `DualMoney` Open book total (Σ per-case booked USD with booked/unbooked note), Paid, Outstanding, FX blocked, Awaiting approval, Outstanding by age, Blocked reasons, evidence mix (open book only, from `/cpor/settlement/book`) |
| Claims evidence, Payments, Plan templates, Terms, Budget ledger | Operational lists. Payments explicitly says delivery rate is "portfolio figure on the domain header — not recomputed here" (`payment-evidence-import/page.tsx:204-205`) |
| Dashboards (Reports) | `support_spend`, `delivery_rate` and `support_cost_per_unit_sold` are `implemented` in `apps/api/app/semantics/catalog/default.yaml:210-290` with handler `a2_cpor.py`. They can be added as widgets through `/api/v1/query/execute` (`DashboardWidgetCard.tsx:38`). `support_norms` and `comparable_cases` are **not** A2 query keys (`query/handlers/__init__.py:23`). Nothing was checked live here, so whether a planner has these widgets by default is unknown. |

### 2c. Overlap matrix

| Figure | Shown elsewhere? | Same computation? |
|---|---|---|
| Delivery rate (all cases) | Yes: FundingChrome meta on every Funding lens | Identical (same endpoint and query key) |
| Support spend total USD/ZAR (all non-superseded cases incl. settled) | Partly. The Case book shows the **open** book only (`/settlement/book`); the dashboards `support_spend` metric has the same handler | Case book: different scope and a better FX method. Dashboards: same |
| Support per unit sold | Only the dashboards `support_cost_per_unit_sold` metric; no Funding lens | Same handler |
| Cost per incremental unit | Nowhere. The semantic catalog marks **A2-X `cost_per_incremental_unit` as `do_not_build`, `refuse_all`** ("no validated baseline/counterfactual model", `default.yaml:~296-304`), yet `incremental_unit_cost.py` (BACKLOG-089) computes it and both panels show it. Live: 192 of 200 cases flagged | Contradiction: a DO NOT BUILD metric |
| Claim-evidenced-only delivery | Nowhere. Live it is null (0 claim-evidenced cases) | — |
| Top BU / top promo spend | Only as dashboard grains of `support_spend` (if allowed_grains include bu/promo_type) | Same handler |
| Support bias planned / actual / % | Yes: Promotion planner HeadlineStrip and PlanWorkspace. The planner deliberately says "Do not divide these two figures", but the panel shows **Bias %** | Same endpoint. The panel adds `limit_cases=100` and a ratio the planner forbids |
| Support norms by customer (trailing 4Q, % of SRP) | **Nowhere mounted.** The endpoint is used by comparables and plan drafts only internally; `PromoPlanBuilderPanel` shows a comparables count only | Unique |

### 2d. The USD issue (booked, None→0): defect or not

- **Booked, not live:** correct for a spend aggregate. Historical support should be valued at each case's booked rate. The Case book does the same (per-case booked USD summed, "never one FX on the ZAR total"). Not a defect.
- **None→0:** a latent defect in presentation. A line with no USD contributes R to `support_zar` but $0 to `support_usd`, and the panels present USD as the primary figure with no unbooked count. `DualMoney` on the Case book instead says "Σ n booked · m unbooked have no USD" and suppresses false precision. **Live impact today is nil:** all 304 cases have `fx_declared=true` (`docs/memory/CURRENT.md:65`), and the book shows 0 unbooked. It becomes real as soon as a floating or unbooked case exists.
- **"R" label:** `support_zar` sums `ttl_support` across cases regardless of `currency_code`, and the panel always prefixes "R". That is wrong if a non-ZAR case exists. Local `fmtUsd`/`fmtZar` also bypass `DualMoney`/`formatLocalMoney`.

### 2e. The lab ("per the lab")

- `design-lab/surfaces/FundingSurface.tsx` lenses are planner, book, settle, claims, payments, templates, pricing and budgets (`:33, 135-146`). `labNav.ts:122-136` lists the same set. **The lab has no portfolio-intelligence lens or panel.**
- The lab places portfolio figures in only two spots:
  - the domain header meta, "delivery rate x%" (`FundingSurface.tsx:122`), which production already has;
  - the Case book "Settled" figure caption, "Delivery rate x%" (`:186`).
- The lab's metric catalog puts `cpor.delivery_rate` and `cpor.support_per_unit` under Reports/dashboards (`design-lab/fixtures/dashboard.ts:37-42`) and marks `cpor.claim_rate` `do_not_build`.
- So "mount per the lab" has no literal target. The lab's nearest home is the **Case book lens**, whose HeadlineStrip already carries a delivery-rate caption, with dashboards as the analytics home.

## 3. Verdicts

### SettlementPortfolioRead: DELETE

- It duplicates `CporPortfolioIntelligencePanel` tile for tile (same endpoint and key).
- Its delivery rate is already on every Funding lens header.
- It lives only inside the orphaned `SettlementContainer` tree, which the lab's settle lens replaced with composition A (`FundingSurface.tsx:149-170`, "Lab composition A is the production desk").
- It shows nothing unique. It also carries the do-not-build incremental-unit tile.
- **Finding:** the rest of that tree is orphaned too. It is out of D-c's literal scope but the same class. Proposal: delete the whole `SettlementContainer` subtree in the same sweep (see §4), with operator ack.

### CporPortfolioIntelligencePanel: MOUNT a trimmed version on the Case book lens

The panel **does** show intelligence that no mounted surface shows:
- support norms by customer (A2-04, `owner_surface: cpor-cases` in the catalog, the case book's route);
- all-lifecycle support spend with support per unit sold (the Case book shows only the open book);
- the top BU/promo split;
- claim-evidenced-only delivery.

By D-c's rule, that means mount, not delete. The lab has no dedicated placement, so the mount target is the **Case book lens** (`/commercial-planner/cpor-cases`). Mount it as one `Panel` "Portfolio read — all non-superseded cases", after the "Outstanding by age / Blocked reasons" grid (`CaseBookSurface.tsx:~612-640`), collapsed by default.

**Required fixes when mounted:**

1. **Remove the "Cost / incremental unit" tile.** The semantic catalog says A2-X is `do_not_build`, and live 192 of 200 cases are flagged. Showing it contradicts the catalog. If Warren wants it, that is a separate decision that must also flip the catalog.
2. **Remove the Support bias section.** It duplicates the Promotion planner, and its Bias % divides the two figures the planner says must not be divided.
3. **Money through `DualMoney`:** `amount=support_zar`, `currencyCode` = tenant currency, `usdAmount=support_usd`, `usdNote="Σ per-line booked USD"`. Also the norms rows and BU line. Drop the local `fmtUsd`/`fmtZar`. Make ZAR (local) primary, consistent with the Case book.
4. **Backend:** return `lines_missing_usd` (the count of the None→0 lines) and a per-currency guard (refuse or split `support_zar` when case currencies differ). Surface the count in the `usdNote`, the same way the Case book shows its unbooked count.
5. **Primitives:** replace MUI `Paper` tiles with a workbench-ui `HeadlineStrip`/`HeadlineFigure` and `Panel`/`PanelRow` (the norms list).
6. **Move** the file out of `app/(app)/commercial-planner/cpor-cases/` into `features/promotions-funding/` (for example `PortfolioReadPanel.tsx`), because it would no longer be an app-route file.
7. **Hide the claim-evidenced-only line when its case count is 0** (live: 0). Otherwise it shows "—".

**Alternative for the operator (recorded, not chosen):**
- Option B: add no Funding placement and rely on dashboards for spend, delivery and support per unit (same handler). Delete the panel.
  - Cost: support norms have no query key, so A2-04 would have no UI anywhere.
- Option C: a new "Intelligence" lens.
  - That departs from the lab and needs a lab update first.
- Option A (the recommended mount above) is the only one that keeps norms visible without new lab IA.

## 4. Files to delete or change, and tests

**Delete (after the ports in §1 land):**
- `features/cpor/CporCaseWorkspace.tsx`
- `features/cpor/CporFxAnchorPanel.tsx` (no referent once the workspace goes, if the port uses HeadlineFigure as recommended)
- `features/settlement/SettlementPortfolioRead.tsx`
- Proposed with operator ack (orphaned subtree; verify by grep again before deleting): `features/settlement/SettlementContainer.tsx`, `SettlementBookRead.tsx`, `SettlementCasePane.tsx`, `SettlementRegimeStrip.tsx`, `SettlementScopeBar.tsx` (+ `SettlementScopeBar.test.tsx`), `SettlementShapeBar.tsx`, `SettlementTaskCrumb.tsx`, `useSettlementBook.ts`, `settlementViews.ts` (+ `settlementViews.test.ts`). Check `workbench-ui/controls.tsx:7,67` comments that name them.
- Keep `CporPaymentEvidencePanel`, `CporPromoLoadPanel`, `CporComparableCasesPanel` and `CporSettleReadinessRow`. They are live through `SettlementCaseTabs`, `PlanWorkspace` and `SettlementConfirmDialog`.

**Change:**
- `features/settlement/mapSettlementDeskView.ts`: new detail fields (approved amount, FX booked/proposed, `needs_reapproval`, `evidence_basis`, `intelligence_exclude`, settlement diagnostics).
- `features/settlement/settlementDeskModel.ts`: `SettlementDeskView` type.
- `features/settlement/SettlementDesk.tsx`: Approved support figure, meta basis line, readiness chips in the Next-action panel, end/cancel actions, reapproval chip, diagnostics chips.
- `features/settlement/SettlementDeskLive.tsx`: transition mutation generalised beyond settle, intelligence-exclude, rollup, out-of-window toggle, and passing `unresolvedProductCount` to the confirm dialog.
- `features/settlement/SettlementCaseTabs.tsx`: `comparables` tab.
- `features/promotions-funding/PlanWorkspace.tsx`: approve-and-book dialog (`fx_rate`, `confirm_over_budget_reapproval`), FX mode and proposed-rate edit for draft/rejected, and a gate or redirect on settle to the desk.
- `features/promotions-funding/CaseBookSurface.tsx`: mount the trimmed portfolio panel.
- `app/(app)/commercial-planner/cpor-cases/CporPortfolioIntelligencePanel.tsx`: move and trim as in §3.
- `apps/api/app/services/cpor/portfolio_intelligence.py`: `lines_missing_usd` and the currency guard.
- Comment references: `features/cpor/CporUsdPivotPanel.tsx:38`, `SettlementCaseTabs.tsx:24`, `SettlementDeskLive.tsx:146`.
- Docs: `docs/BACKLOG.md` BACKLOG-202 → closed, `docs/memory/CURRENT.md:62,65`, `docs/audits/GRID_AND_COLUMN_PARITY_AUDIT.md`, and design docs that name the files (`docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md`, `IMPLEMENTATION_PLAN.md`, `STAGED_WORK_PLAN.md`).

**Tests:**
- `app/(app)/commercial-planner/cpor-cases/[id]/page.fxReadiness.test.tsx` renders `CporCaseWorkspace caseId={312}` and mocks `CporPaymentEvidencePanel` to null. Retarget it to `SettlementDeskLive` and assert the ported pieces: readiness chips, approved-support `DualMoney`, the FX basis line, and settle hidden when `fx_settle_allowed=false`.
- Extend `features/settlement/SettlementDesk.test.tsx` for end/cancel visibility from `allowedNext` and the reapproval chip.
- Extend `SettlementCaseTabs.test.tsx` for the comparables tab.
- Extend `CaseBookSurface.test.tsx` for the portfolio panel mount (no incremental tile, DualMoney).
- `SettlementScopeBar.test.tsx` and `settlementViews.test.ts` are deleted along with the subtree.
- No existing test references `SettlementPortfolioRead` or `CporPortfolioIntelligencePanel`.
- `fxDisplay.test.ts` stays.

## Findings for the programme (finding.defer / decision candidates)

1. **Decision, operator:** where portfolio intelligence mounts. The lab has no placement. Recommendation: Case book panel (Option A). Alternatives are dashboards only (B) and a new lens with a lab update first (C).
2. **Contradiction:** the `cost_per_incremental_unit` catalog entry (A2-X) is `do_not_build`, but BACKLOG-089 code computes it and both orphan panels show it.
3. **Gap:** approve-and-book-FX (`fx_rate`), over-budget reapproval confirmation, the intelligence-exclude switch, re-rollup, the FX mode toggle and proposed-rate edit exist only in the unmounted workspace. They are UI-unreachable today, not just after the delete.
4. **Risk:** `PlanWorkspace` exposes `settle` without the FX readiness gate or the confirm dialog (`PlanWorkspace.tsx:283-286`).
5. **Orphan subtree:** the `SettlementContainer` tree (9 files and 2 tests) is unmounted.
6. **Design-system:** `CporSettleReadinessRow` uses hard-coded hex colours.
7. **UNABLE_TO_RENDER:** the desk in a background MCP tab (stuck on "Loading case…" while the API answered in about 300 ms). A foreground smoke is needed at implement/validate.
