# Step 4b

- **Status:** Code written in the cloud. Not merged, not deployed, no visual gate.
- **Branch:** `fix/theme-shared-components-20261126` (from `origin/feat/integrate-20261103` at `643b2892`)
- **Worktree:** cloud checkout
- **PR:** https://github.com/IoTWazPresales/channel-intelligence-platform/pull/133 — `[CODE ONLY] U5` against `feat/integrate-20261103`
- **Commits:** the U5 commit on that branch

## Checklist

- [x] Read `docs/handoffs/2026-11-24/RULES.md` and the U5 prompt in `docs/handoffs/2026-11-27/CLOUD-CLOSE-OFF.md`
- [x] Theme through shared components. This chat is the one slice: page title element, dead tone selector, directory title, panel title weight and shadow, rail count chip.

## What landed

- `PageHeader` renders `variant="h1" component="h1"`. Warren 26 Nov: "Yes" — the test asserts `h1` because the dashboard-v2 mock-up title is an h1.
- Empty `crumbs` render no breadcrumb row, so `/directory` can use `PageHeader` without inventing a trail.
- `DomainHeader` sets `component="h1"` (it already used `variant="h1"`).
- `data-cip-tone` rules are gone from `cipTheme.ts`, and the test no longer asserts `&[data-cip-tone]`.
- `/directory` title is `PageHeader` / theme h1. `/promotions` was not touched (U2).
- Panel titles use theme `panelTitle` (weight 650, 14px, line-height 1.3) and `boxShadow: var(--shadow)`. `--shadow` is the dashboard-v2 token on `body`, dark and light. `MuiPaper` reads the same variable.
- Rail stays 244px. A three-digit count uses chip padding 4px, row gap 2px, chevron box 16px. The label ellipsizes if the font is wider than the measured Inter. Count chip and chevron do not shrink.

## ASSUMPTIONS

- "Dead data-cip-tone selector" means every rule that keys off that attribute, including the `::before` accent rails. Search of `apps/` and `packages/` `*.ts`/`*.tsx` found the attribute only in `cipTheme.ts` and its test.
- Panel title size stays 14px (`0.875rem`, the old `subtitle2`). Only the weight moves to 650. The mock-up `.panel-head h2` is 13px; that size change was not in the U5 sentence.
- The panel title element is `h2` (mock-up panel head). `subtitle2` had been rendering an `h6`.
- Directory has no breadcrumb. `PageHeader` with `crumbs={[]}` is the shared title, not a new trail.
- Rail chip `sx` padding overrides the theme chip label padding of 9px. The 26 Nov fit at 244px only holds if it does. The rail chip now uses `&& .MuiChip-label` so the 4px padding wins.
- Label 154.2px is the 26 Nov Playwright measurement. "999" is 18.9px from Inter Medium at 10px (fontTools, 27 Nov 2026, this cloud machine). Spare at those widths is 4.9px inside the 206px heading row.

## STOP items waiting for Warren

None. No schema change. Live `cip` writes stay stopped. `/promotions` title waits for U2.

## Gates run

Cloud Linux, no `cip` database.

- `pnpm --filter @cip/web exec vitest run` — 1942 passed, 3 failed. One failure was `Panel.test.tsx` asserting computed `fontSize` `14px`; jsdom returned `0.875rem`. The assertion was changed to `0.875rem` and that file re-run (see the commit). The other two failures were not edited.
- `pnpm --filter @cip/web exec tsc --noEmit` — exit 0.
- eslint on the U5 files (flat config) — exit 0.
- Failures not caused by this diff: `FundingChrome.test.ts` expects `RAIL_WIDTH` 172 while the rail is 244 (U2 owns that file). `StockNotListedWorklist.test.tsx` fails on customer-search URL shape (`page_size=25` vs `200`, encoding). U1 owns market-listings. Neither file was edited.

## Live proof

None. No visual gate in the cloud.

## Resume notes

Do not open a second branch. Local finishing: visual gate (dark and light) on a `PageHeader` page, `/directory`, a `Panel`, and the rail with a three-digit count beside Promotions & Funding. Then review, merge to `feat/integrate-20261103`, deploy. Update `docs/memory/CURRENT.md` at merge — this cloud unit did not, because other units write that file in parallel.
