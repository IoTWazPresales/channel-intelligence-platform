# GOV-008 independent review: N-0044 (R2, ui)
Reviewer: verification-controller, run separately from the implementation run. Lenses used: product-interaction-designer, frontend-engineer, accessibility-specialist, analytics-bi-specialist. I did not read IMPL.md.
Evidence: commit 657dd1ed; the deleted files pulled with `git show 657dd1ed^:` into this folder (old_workspace.tsx, old_fxanchor.tsx, old_portfolioread.tsx); the running app on 127.0.0.1:3000 in my own Chrome tab (closed afterwards); read-only SQL through ro_sql.py.
Labels: VERIFIED means I observed it myself. ASSERTED means I did not.

## 1. Desk: FX anchor, settle readiness, comparable cases, transition buttons (PASS, with limitation on 311)
- VERIFIED live on /commercial-planner/cpor-cases/46. DB state: status=ended, needs_reapproval=True, fx_mode=booked, roe 19.14.
  - "APPROVED SUPPORT R 1,517,439.79 / $ 79,361.28 · Σ line USD at the booked rate / Booked 19.14 · booked · by Local Admin · 2026-09-06".
  - Header meta shows "FX basis: booked · ROE ZAR 19.14/USD".
  - The needs-reapproval banner is shown.
  - `group "Settle readiness"` (role=group, aria-label) holds the chips "Assumptions clear" and "No claim files · not source-attested".
  - Header actions: "Cancel case…", "Supersede…" and the primary CTA "Upload customer report".
  - "End case…" is correctly absent: the case is already ended.
  - The Comparable cases tab rendered a ranked list of 382 candidates.
- Code, SettlementDesk.tsx:139-146:
  - End and Cancel appear only when `allowedNext` has ended or cancelled.
  - Settle is enabled only when canSettle && fxSettleAllowed && allowedNext.includes('settled') && handler.
  - Pre-approval actions go to the planner through the "Open in planner" link.
- Confirmation, SettlementDeskLive.tsx:39-52 and 261-294: End and Cancel go through a Dialog (aria-labelledby, "Keep case" button, copy saying cancel is terminal). Settle uses the existing SettlementConfirmDialog.
  - VERIFIED live: I opened "Cancel case…", the dialog rendered, and I closed it with Escape.
  - A DB re-read shows case 46 still `ended` with updated_at unchanged (2026-09-06).
- LIMITATION, 311: the desk /commercial-planner/cpor-cases/311 (settled, booked 16.50) stayed on "Loading case…" (ModuleDataSection gate) for more than 60 s on 3 attempts.
  - At the same time /promotions?plan=311 loaded the same case detail, and API :8001/health returned 200 in 6 ms.
  - The stall is probably the /settlement query for 311. The commit changed no API code.
  - Recorded as UNABLE_TO_RENDER for 311, plus a finding: the loading state never times out.

## 2. CporCaseWorkspace deleted with nothing lost (PASS)
Capabilities of the deleted workspace (old_workspace.tsx) and where each lives now:

| Old capability | Now | Evidence |
|---|---|---|
| Approve-and-book-FX dialog (fx_rate) | PlanWorkspace dialog "Approve {code} and book FX", field "Booked ZAR per USD", posts fx_rate | 657dd1ed PlanWorkspace diff; testid plan-approve-fx-rate |
| Over-budget reapproval (confirm_over_budget_reapproval) | PlanWorkspace: button reads "Reapprove (over budget)", payload `confirm_over_budget_reapproval: Boolean(needs_reapproval)`, plus the plan-needs-reapproval Alert; the desk also shows the banner | code; banner live on 46 |
| Intelligence-exclude switch (POST intelligence-exclude, confirm:true) | Desk "Claims & intelligence" switch, same endpoint | SettlementDeskLive.tsx:109; live on 46 |
| Re-rollup (POST settlement/rollup) | Desk "Re-rollup from claims" | SettlementDeskLive.tsx:100; live |
| Out-of-window include (import form field) | Desk checkbox, same include_out_of_window form field | SettlementDeskLive.tsx:73-77 |
| FX mode toggle (PATCH fx_mode) | PlanWorkspace FX mode booked/floating (aria-pressed; editable in draft/rejected) | live on plan 311: "FX mode booked floating Booked 16.50 by Local Admin" |
| Proposed-rate edit (PATCH fx_proposed_rate) | PlanWorkspace "Proposed ZAR/USD" plus "Save proposed" (draft/rejected) | code |
| propose / approve / reject (comment) / resend / activate | PlanWorkspace, which already had them; reject needs PM feedback | PlanWorkspace.tsx:304, 341, 684-705 |
| end / cancel | Desk, with a confirm dialog | above |
| settle | Desk only (PlanWorkspace filters settle and links to the desk) | diff |
| Claim-evidence import and summary | Desk "Upload customer report" plus the import-summary Alert | SettlementDeskLive.tsx:77, 211 |
| CporFxAnchorPanel | Desk Approved-support DualMoney figure plus FX basis line | live |
| CporSettleReadinessRow, CporComparableCasesPanel | Desk (Next-action readiness chips; Comparable cases tab) | live |
| Tabs: USD pivot, Events, Exports, Promo load, Payments/recon | SettlementCaseTabs on the desk | live |
| Lines grid, Add line | PlanWorkspace lines grid and Add line dialog | PlanWorkspace.tsx:154, 545, 792 |
| Settlement tab chips (claims, out-of-window, unresolved, CST) | Desk Evidence chips | live |
| PM last comment; missing ROE | PlanWorkspace plan-last-comment; DualMoney missingRoe | diff |

- Minor finding, not blocking: the old Settlement-tab grid had per-line "Ttl result (local)" and "Ttl result USD".
  - The desk grid shows quantities and corroboration per line, with money only as aggregates (CIP reconciled / Agreed / HQ credit tiles).
  - The old status, workflow, export-version and flag chips are also not reproduced one to one.
- Remaining references are comments or test names only. Grep for CporCaseWorkspace, CporFxAnchorPanel, SettlementPortfolioRead and CporPortfolioIntelligencePanel finds no imports.

## 3. SettlementPortfolioRead deleted; the rest of the orphan subtree kept (PASS)
- The file is deleted and its only mount was removed from SettlementBookRead.tsx.
- It read /cpor/intelligence/portfolio as 4 tiles: support spend, delivery rate, support/unit, cost/incremental unit. The same endpoint also feeds FundingChrome and the new PortfolioReadPanel, so deleting it as a duplicate is justified.
- The rest of the subtree is still present in features/settlement: SettlementContainer.tsx, SettlementCasePane, SettlementScopeBar, SettlementRegimeStrip, SettlementShapeBar, SettlementTaskCrumb and the others (ls, VERIFIED).

## 4. Portfolio panel: unique, collapsed on the Case book, uses DualMoney (PASS)
- VERIFIED live on /commercial-planner/cpor-cases:
  - The panel "Portfolio read — all non-superseded cases" renders collapsed with a "Show" button.
  - After expanding: aria-expanded=true and aria-controls resolves.
  - The body and its queries mount only when the panel is opened.
- Expanded, it read:
  - "304 cases · 621 lines · voided excluded · mixed evidence: claim 0 · attested 230 · none 74".
  - SUPPORT SPEND R 28,862,697.61 / $ 1,617,054.49 · Σ per-line booked USD.
  - DELIVERY RATE 61.8% (Result 29 970 / est 48 463).
  - SUPPORT / UNIT SOLD R 963.05 / $ 53.96.
  - Top BU NB R 23,128,774.09 / $ 1,294,017.27.
  - Top promotion type Sell out PP R 12,164,967.15 / $ 689,440.48.
  - Support norms by customer, trailing 4Q.
- Referent check with ro_sql:
  - Non-superseded, non-excluded, non-voided cases: count(distinct case)=304 and sum(ttl_support)=28,862,697.61. Both match exactly.
  - My line count was 652 against 621 shown. My query did not exclude voided lines; the panel says voided lines are excluded, so this is ASSERTED as the explanation.
- Unique intelligence: the panel covers every lifecycle stage, while the Case book open book is a narrower scope. It adds support/unit, top BU, top mechanic and customer norms, which no other surface I inspected shows (ASSERTED beyond those surfaces).
- The cost-per-incremental-unit and support-bias blocks were trimmed, with a stated reason in the code comment.
- Analytics nit: the thousands separator is a space in fmtInt ("29 970") but a comma elsewhere ("1,643").

## 5. ModuleDataSection, no migrations, read-only on cip (PASS)
- ModuleDataSection is used in:
  - the desk gate (SettlementDeskLive.tsx:154);
  - CporComparableCasesPanel (converted in this commit, with empty/error/retry states);
  - PortfolioReadPanel (2 sections).
- The commit stat touches only apps/web and docs/BACKLOG.md. It has no alembic or API changes.
- During my session, cases 46 and 311 kept their updated_at values.

## 6. Tests, tsc, backlog (PASS)
- `pnpm --filter @cip/web exec vitest run src/features/settlement src/features/promotions-funding src/features/cpor "src/app/(app)/commercial-planner/cpor-cases"`: 25 files and 89 tests passed, EXIT 0 (vitest.log).
- `tsc --noEmit -p .`: EXIT 0 (tsc.log).
- docs/BACKLOG.md for BACKLOG-202 now reads "Closed — workspace retired (2026-09-24 N-0044, operator decision D-c)" with a what-moved-where list.

## 7. Accessibility of the new desk pieces and the Comparable cases tab (FAIL, narrow)
- Good:
  - The case tabs are an MUI tablist with aria-label "Case detail" and roving tabIndex. Each tab has an id and aria-controls, and the tabpanel's aria-labelledby resolves. There is a visible focus outline.
  - The readiness chips sit in role=group with an aria-label.
  - The lifecycle dialog is labelled and closes on Escape.
  - The switch and checkbox get their accessible names from FormControlLabel ("Exclude from intelligence (comparables, norms, book totals)").
  - The portfolio toggle uses aria-expanded and aria-controls.
- **FAIL: text contrast.** The labels of the two new desk controls, "Include out-of-window rows on the next upload" and "Exclude from intelligence …", use Typography variant caption. The theme's caption color is `text.muted` (cipTheme.ts:35).
  - Measured in the DOM: color rgba(160,176,192,0.55) on panel background rgb(34,38,46), 12px text. That is about 3.1:1, below the WCAG 1.4.3 minimum of 4.5:1.
  - These are labels for interactive controls. Fix: body2 or text.secondary in SettlementDesk.tsx:610 and :628.
  - The retired workspace used the same pattern, so this is not a regression. It still fails the criterion for the new desk pieces.
- The 390x844 viewport was not attempted (resize is known not to work here), so it is UNABLE.

## Other findings (not blocking)
- Comparable-case rows show the customer as a code ("CUST-000045"), not a name. This is a pre-existing panel, but it breaks the entity-code display rule.
- On case 46 (ended) the banner says "reapprove … in the planner", but the desk shows no "Open in planner" link because allowedNext has no planner target. For an ended case this is a dead end.
- On PlanWorkspace, the link to the desk is labelled "Settlement workspace", naming the retired concept, when the case cannot settle. The desk's own crumb is "Settle a case".
- The desk description still says "Ken's desk: …" (pre-existing since b1696b02).
- The desk grid on 46 leaves a large empty band because of its fixed 360px height with 5 rows.
- The desk loading state for 311 never resolved and never timed out (see criterion 1).

## Overall verdict: FAILED
There is one narrow, easily fixed accessibility defect (criterion 7: control-label contrast about 3.1:1). Criteria 1-6 pass. The desk for case 311 could not be rendered (limitation).
