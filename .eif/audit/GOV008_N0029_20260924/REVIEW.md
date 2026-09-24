# GOV-008 independent review: N-0029 (R2, ui)

"Grid community clipboard in one wrapper, Case book working content first"

- Reviewer: independent GOV-008 run (fresh context). Lenses: verification-controller, ui-visual-design-specialist, product-interaction-designer, frontend-engineer.
- Independence rung: another session (fresh context), same model family. This is acceptable for R2.
- Prior findings folders and handover docs were not read, as the brief requires.
- Date: 2026-09-24. Branch `feat/ns-2-brief-nav-collapse`, HEAD 6b34dea8.
- Everything below is read-only. SQL went through `ro_sql.py` (it printed `current_database() = cip`). I clicked no control that writes data.

## Evidence base
- Commits: fc15436a ("Case book grid-first and community grid text selection"), aee82a72 ("honour payment-evidence ?code= exact Case ID"), 5e70f33a (the later grid-height single source, which is context only).
- Tests (VERIFIED): I ran `npx vitest run` in apps/web on EnterpriseDataGrid.test.tsx (3), paymentEvidenceCode.test.ts (3), payment-evidence-import/page.test.tsx (2), PaymentEvidenceOverlay.test.tsx (1) and CaseBookSurface.test.tsx (1). All 5 files and 10 tests passed. The first combined run also reported 1 unrelated vitest cache `writeFile` error, which is sandbox noise; the suites still passed.
- Rendered: Claude-in-Chrome, in my own tab (closed at the end), against http://127.0.0.1:3000. The session was signed in as Local Admin.

## AC1: one community wrapper. PASS (VERIFIED)
- `git grep "AgGridReact|from 'ag-grid"` over apps/web/src finds only one production import: `apps/web/src/components/EnterpriseDataGrid.tsx:6`. The other hits are test mocks and a comment in design-lab.
- EnterpriseDataGrid.tsx:18 has `ModuleRegistry.registerModules([AllCommunityModule])`. Lines 133-134 set `enableCellTextSelection` and `ensureDomOrder` after the `{...restGridOptions}` spread, so a caller cannot turn them off.
- Line 91 sets `cursor: clickableRows ? 'pointer' : 'default'`, where clickableRows means `typeof onRowClicked === 'function'`. In the rendered Case book the `.ag-row` computed cursor is `pointer`.
- There is no `ag-grid-enterprise`, `enableRangeSelection`, `cellSelection` or `exportDataAsExcel` anywhere in apps/web/src or package.json (grep returned 0 hits).
- MasterColumnPickerDialog (components/masterGrid) and ColumnSelectorModal (features/commercial-planner) remain separate files. They were not unified.

## AC2: Case book composition. PASS (VERIFIED)
- CaseBookSurface.tsx renders in this order: HeadlineStrip (436), then the lifecycle block (505-525), then ScopeBar (527), then ModuleDataSection with EnterpriseDataGrid (547-608), then PaymentEvidenceOverlayPanel (610), then the ageing and "Blocked cases" panels (612+).
- The lifecycle block is a `Typography variant="caption"` ("Settlement half of the same lifecycle ... unmatched Case IDs are below the grid") above a dense LifecycleRail. It is not an Alert. The only Alert on the book sits inside the overlay, at y=1214, below the grid bottom at y=1073.
- LifecycleRail can still be reached. EntityContextPanel is at 736. `CporCaseWorkspace` does not appear in the file, and no `[data-testid*=workspace]` element is in the DOM. The CaseBookSurface test "does not mount the settlement desk" passes.
- Observation: the lifecycle caption and rail sit between HeadlineStrip and ScopeBar. The criterion allows this ("LifecycleRail stays reachable"), but it pushes the grid down (see AC4).

## AC3: unmatched and pending Case ID rows are clickable. PASS (VERIFIED)
- PaymentEvidenceOverlay.tsx `paymentEvidenceRowHref` returns `?case=<id>` when case_id is set and `/commercial-planner/cpor-cases/payment-evidence-import?code=<encoded>` otherwise. Both the pending Latest Comment PanelRows and the unmatched PanelRows pass `href` to it. PanelRow (workbench-ui/Panel.tsx:108) renders a NextLink.
- Rendered overlay: there are 28 links. 12 are unmatched rows, all using `?code=`. The pending rows include 2 linked ones (`?case=244`, `?case=259`).
- **Click test on an unmatched row:** I clicked "C19B54067 · Source attested" (RECTRON, closed, $15k). The URL became `/commercial-planner/cpor-cases/payment-evidence-import?code=C19B54067`.
- **Does the payment-evidence page read ?code=? YES.** page.tsx:67-68 reads `useSearchParams().get('code')` into `parseExactPaymentEvidenceCode`, then queries `/overlay?code=`. The rendered focus Alert says: "Case ID C19B54067 — exact match only. This page does not mint a CIP case. 1 applied evidence row(s)." One match card shows "RECTRON (PTY) LTD · closed · $15k · unlinked".
- Exact match only: `?code=c19b54067` (lowercase) renders "No applied payment-evidence row has this Case ID." with 0 matches. The backend `exact_case_code` only trims, then does ORM equality on `external_case_code` (aee82a72, overlay_read.py).
- No case minted: `ro_sql` returned `minted=0` from cpor_case where case_code in ('C19B54067','c19b54067'), and 1 row in cpor_payment_evidence. The row stays reviewable and unlinked: flagged, not blocked.
- **Click test on a linked row:** I clicked pending "C25B01857 · to_be_clarified" (labelled "linked"). The URL became `/commercial-planner/cpor-cases?case=244` and the EntityContextPanel drawer opened on "C25B01857 · Makro".
- Tool note: the first click by element ref only scrolled the row into view. A coordinate click navigated. I found no product defect behind this.

## AC4: 1280x800, grid visible before the overlay above the fold. PASS with limitation (VERIFIED)
- `resize_window(1280,800)` reported success, but the page's CSS viewport stayed 1707x876 (DPR 1.5). I therefore used an exact-size **same-origin iframe of 1280x800** on /commercial-planner/cpor-cases, as the prompt allows.
- DOM measurements in the iframe at scrollY=0:
  - The book starts at 285, the lifecycle block at 479, and the **grid top at 722**.
  - The header row occupies 722-763. The first data row occupies 763-803, so about 37 of its 40px are visible.
  - The **overlay top is 1157**, below the fold. Zero data rows are fully visible.
- The criterion as written holds: the grid starts above the fold and the overlay does not. The quality concern is that at 1280x800 the user sees the grid header plus a clipped first row, not working rows. The page header, tabs, the 5-card HeadlineStrip (about 150px), the lifecycle caption and rail, and the two-row ScopeBar filter block use about 720px.
- At the operator's native viewport (1707x876 CSS) the grid top is 655 and several rows are visible.

## AC5: select text in a grid cell. PASS (VERIFIED), with one interaction finding
- The computed `user-select` on `.ag-cell` is `text`.
- A real mouse drag across the Owed cell of row 0 fired `selectionchange`. `getSelection()` returned "6,231.52 · $ 9", and the selection persisted afterwards.
- Finding (product-interaction, minor, not a failure of this criterion): because the grid has `onRowClicked`, the mouseup that ends a text drag also counts as a row click. It opens the case drawer (`?case=311`). The same thing happened on a double-click attempt. Copying from a cell therefore always opens the drawer too. Suggested fix: in the Case book `onRowClicked`, skip `setParams` when `window.getSelection()?.toString()` is non-empty. This is a common pattern for grids that combine selection with row click.

## Other observations (not scored)
- a11y:
  - The PanelRow links have accessible names from their primary text (for example "C25B01857 · to_be_clarified"). This is adequate.
  - The case grid rows open the drawer on pointer click only. `onRowClicked` does not fire on keyboard Enter in AG Grid community. Keyboard users rely on the mobile card path or other routes. This predates the node's scope. ASSERTED from AG Grid behaviour; I did not keyboard-test it.
- Content:
  - The copy stays honest: "exact match only", "does not mint a CIP case", "not minted as cpor_case".
  - The drawer for case 244 shows status SETTLED alongside "OUTSTANDING R50k". This looks inconsistent, but it is outside this node's scope, so I record it as an observation only.
- Design signatures observed: `grid_above_fold` holds marginally at 1280x800 (header plus clipped row). `unmatched_case_id_link` is present and working. `payment_evidence_reads_code` is present and exact-only. `lifecycle_caption_not_alert` is present. `pointer_cursor_on_clickable_rows` is present. `single_community_grid_wrapper` is present.

## Overall verdict: VERIFIED_WITH_LIMITATIONS
All 5 criteria pass. The limitations:
1. The 1280x800 check used a same-origin iframe because window resize did not change the CSS viewport.
2. At 1280x800 only the grid header and a clipped first row are above the fold. The criterion holds as written, but the grid-first intent is only thinly met.
3. Dragging to select cell text also opens the case drawer.
4. The independence rung is fresh-session, same model.
