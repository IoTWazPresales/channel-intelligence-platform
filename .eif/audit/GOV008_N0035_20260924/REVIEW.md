# GOV-008 independent review: N-0035 (R2, ui)
"Stage 2.2/2.3: grid-scoped 13px type token and density 40/40"

Reviewer: independent GOV-008 session (fresh context; lenses verification-controller, ui-visual-design-specialist, accessibility-specialist, frontend-engineer). Rung used: R2, another session with fresh context, same model family (not another model). I did not read the implementer's findings (docs/memory CURRENT/CONTEXT 2026-09-22 entries).
Date: 2026-09-24. Read-only: no product edits, no DB access, no sign-in, and the density toggle was not touched.

## Evidence base
- `git show a4fe957f` (2.2): `packages/ui/src/agGridMuiTheme.ts` adds `export const AG_GRID_FONT_SIZE = '13px'` and sets `'--ag-font-size': AG_GRID_FONT_SIZE`. It removes the line `const fontSize = typeof theme.typography.body2?.fontSize === 'string' ? ... : '0.8125rem'`. `packages/ui/src/index.ts` re-exports `AG_GRID_FONT_SIZE`. VERIFIED.
- `git show 459f4c94` (2.3): `apps/web/src/theme/gridDensity.ts` changes `comfortable` from `{42,42}` to `{ rowHeight: 40, headerHeight: 40 }`. The `compact: { rowHeight: 34, headerHeight: 36 }` line is untouched context in the diff. The rest of the change is comments. VERIFIED.
- body2 in cipTheme: neither commit touches `apps/web/src/theme/cipTheme.ts` (both `git diff --stat` outputs are empty). The file's last commit is 2e0c2a2c, which is earlier. The body2 override there is only `body2: { color: t.text.secondary }` (cipTheme.ts:34), with no fontSize. VERIFIED.
- Current HEAD state: agGridMuiTheme.ts:19 `AG_GRID_FONT_SIZE = '13px'`, :44 uses it. index.ts:4 exports it. gridDensity.ts has comfortable 40/40 and compact 34/36. The only other `--ag-font-size` writer is `apps/web/src/design-lab/surfaces/DensitySurface.tsx:116`, which is a design-lab comparison surface and not a product grid. VERIFIED.
- Tests and types (re-run in this session, outputs in this folder):
  - `pnpm --filter @cip/web exec vitest run src/theme src/components`: 13 files, 34 tests passed, EXIT 0 (vitest.txt). VERIFIED.
  - `pnpm --filter @cip/web exec tsc --noEmit`: EXIT 0, no output (tsc_web.txt). VERIFIED.
  - `pnpm --filter @cip/ui exec tsc --noEmit`: EXIT 0 (tsc_ui.txt). VERIFIED.
  - Gap: no unit test asserts the GRID_DENSITY values or AG_GRID_FONT_SIZE. A grep for test files referencing GRID_DENSITY, gridRowMetrics, gridDensityCssVars or AG_GRID_FONT_SIZE found none. Compact 34/36 is therefore verified from code and the diff only, as the brief instructs.

## Rendered measurements (own Chrome tab, 127.0.0.1:3000, viewport 1707x876 CSS px, dark theme)
Measured on each `.ag-root-wrapper`: computed custom properties, the first 5 `.ag-row` rect heights, the `.ag-header-row` height, the first data cell's computed font-size/line-height, and a vertical-overflow count over the first 60 cells (scrollHeight > clientHeight+1).

| Surface | --ag-font-size | --ag-row-height | --ag-header-height | row rects | header | cell font / line-height | clipped |
|---|---|---|---|---|---|---|---|
| /admin/customers | 13px | 40px | 40px | 40 x5 | 40 | 13px / 37px | 0 |
| /plan-vs-executed (redirects to /stock?lens=execution), grid 0 | 13px | 40px | 40px | 40 x5 | 40 | 13px / 37px | 0 |
| same page, grid 1 | 13px | 40px | 40px | 40 x5 | 40 | 13px / 37px | 0 |
| /commercial-planner/cpor-cases/46 (Case book "Settle a case", C24446638) | 13px | 40px | 40px | 40 x5 | 40 | 13px / 37px | 0 |
| /admin/customers in a 390x844 sandboxed iframe (see below) | 13px | 40px | 40px | 40 x4 | 40 | 13px | 0 |

All VERIFIED. Note: /plan-vs-executed is now a redirect to /stock?lens=execution. I measured the grids on that page.

- Zoom screenshots (/admin/customers header and 4 rows; case 46 SKU grid header and 5 rows): glyphs are fully inside the rows, with no top or bottom clipping, the text is vertically centred, and header labels and filter icons fit in 40px. Some SKU and Product cells end in horizontal ellipsis ("90NB0TY1-M04..."). That comes from column width, not this node's change. VERIFIED.
- Non-grid body2: `.MuiTypography-body2` elements outside `.ag-root-wrapper` computed at 14px, e.g. the case 46 subtitle "Sell-Through PP · 2024-04-23 ->", the /stock header text "Distributor and retailer stock", and nav labels. body2 is unaffected. VERIFIED.
- 390x844: I did not resize the window, because it is shared with other reviewers and resize is reported not to work. First attempt: a plain same-origin iframe of /admin/customers. The app navigated the top frame (frame-busting), so it failed. Second attempt: a sandboxed iframe (`allow-scripts allow-same-origin allow-forms`, no top-navigation) of exactly 390x844. It rendered, with inner window 390x844, and the grid measured 13px / 40 / 40 with no clipping. This is an iframe emulation, not a real device viewport. Observation outside this node's scope: at 390px the desktop sidebar stays fully expanded (about 230px), so the page content and grid are cut off on the right. That is a responsive shell issue, not caused by type or density tokens.

## Criteria
1. AG_GRID_FONT_SIZE 13px, grid-scoped, in packages/ui, exported from @cip/ui, not derived from body2, with body2 outside grids unaffected: **PASS** (code + diff + rendered 13px in grids and 14px body2 outside them).
2. GRID_DENSITY comfortable 40/40 with compact unchanged 34/36 in apps/web/src/theme/gridDensity.ts: **PASS** (diff + HEAD file). Compact is verified from code only, with no unit test pinning it.
3. Browser-verified: **PASS** on 4 grids across 3 routes (40px rows and header, 13px, no vertical clipping). 390x844 is only via the sandboxed-iframe emulation.

## Lens notes
- UI visual: 13px on a 40px row (37px line-height) reads cleanly, and compact 34/36 is still a visible step. No regressions seen.
- Accessibility: 13px is below the 14px body text elsewhere but still within common data-grid practice. Text is not clipped. Row height is 40px, and header controls fit. Zoom and reflow at 200% were not tested (limitation).
- Frontend: one source for each token. The EnterpriseDataGrid inline vars match the computed CSS vars. The dead packages/ui height emission was removed later in 99a89db8, which is out of scope here.

## Verdict: VERIFIED_WITH_LIMITATIONS
Limitations: R2 independence is a fresh session with the same model family. The 390x844 check was an emulated sandboxed iframe, not a real viewport. Compact 34/36 is verified from code only, with no test pinning the values, and was not rendered. 200% zoom was not tested. The dark theme only was rendered.
