# N-0029 implementer evidence — grid clipboard and Case book working content

**Run:** `NS17_GRID_CASEBOOK_20260915` · **Actor:** `gov-001` · **2026-09-15**
**Do not complete.** Independent GOV-008 is a later session, different run and actor.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip`. No SQL.

Cites **D-0008** (accepted). **N-0027** StewardFailureQueue remains an `EnterpriseDataGrid` consumer. **N-0028** Start work / Lineup cases not reverted. N-0025 GOV-008 leftovers not remediated.

Reconcile: `.eif/audit/NS17_GRID_CASEBOOK_20260915/RECONCILE.md`.

---

## Charter (re-read from ledger before land)

N-0029: community clipboard in `EnterpriseDataGrid` only (`enableCellTextSelection` + `ensureDomOrder`; pointer cursor when `onRowClicked`). Case book: HeadlineStrip then ScopeBar then grid first; overlay and ageing below; Alert is a caption. Unmatched Case ID rows clickable into existing destinations. Settlement `/cpor-cases/<id>` UNCOVERED. No range/Excel. No dual column-picker merge. Do not complete. Do not run GOV-008.

---

## Playwright 1280×800 (VERIFIED)

| Step | Result |
|---|---|
| `/commercial-planner/cpor-cases` | Headline **Open book total R4.4m** · 74 non-settled cases. Caption + LifecycleRail. ScopeBar (Ended · 74, 304 of 304 cases). **Grid immediately after ScopeBar.** Overlay paid-note and unmatched list **after** the grid. Ageing after overlay. |
| Unmatched row `C19A50693 · Source attested` | Link. Click → `/commercial-planner/cpor-cases/payment-evidence-import?code=C19A50693`. Existing payment-evidence steward. **Not minted** as `cpor_case`. |
| Settlement desk `/cpor-cases/<id>` | Not opened. **UNCOVERED** — no lab render. |

`payment-evidence-import` does not read `?code=` (VERIFIED no `searchParams` in that page). Land is the steward; token filter is BACKLOG.

---

## Product land

| Path | Role |
|---|---|
| `apps/web/src/components/EnterpriseDataGrid.tsx` | Community cell text selection + DOM order; pointer cursor when row click is supplied |
| `apps/web/src/features/promotions-funding/CaseBookSurface.tsx` | Strip → caption/rail → ScopeBar → grid → overlay → ageing |
| `apps/web/src/features/promotions-funding/PaymentEvidenceOverlay.tsx` | `paymentEvidenceRowHref`: linked `?case=`; unlinked import `?code=` |

vitest: EnterpriseDataGrid, PaymentEvidenceOverlay, CaseBookSurface — **5 passed**.

---

## Routed out (BACKLOG)

Settlement workspace design; dual column pickers; AG Grid Enterprise range/Excel; Lineup ApprovalBadge leftover; other chrome-below-fold surfaces; import `?code=` consume.

D-0002 / N-0006 / N-0013 / D-0010 / BACKLOG-181 / Movement/Execution / N-0025 remediation untouched.
