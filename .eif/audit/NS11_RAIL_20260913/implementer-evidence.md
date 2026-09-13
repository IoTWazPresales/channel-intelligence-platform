# N-0023 implementer evidence — BACKLOG-181 rail port

Run `NS11_RAIL_20260913` / actor `gov-001`. Independent GOV-008 not recorded.

## Governing source

`apps/web/src/design-lab/shell/LabShell.tsx` commits `1f434e4`, `130189e`.
Production `apps/web/src/features/shell/CapabilityRail.tsx`.

Do not cite a frozen design-language version or grammar number.

## Token port (VERIFIED Playwright, no browser_cdp)

Viewport 1280×800 `/stock?lens=cover` after port, vs lab `/design-lab/stock?lens=cover`:

| Token | Lab | Production after port |
|-------|-----|------------------------|
| Expanded header bg | `rgb(34, 38, 46)` sticky z-index 2 | same |
| Active leaf bg | `rgba(0,0,0,0)` | same |
| Leaf `::before` | 3×15px r=2 `rgb(61, 184, 232)` | same |
| Nested list `borderLeft` | 0, `marginLeft` 34px | same |
| Header/leaf right edge | aligned (lab 243.33, prod 228 — badge/session chrome) | aligned to each other |

390×844 drawer (visible rail of 2 in DOM): same 3×15 bar, raised header, no guide rail.

Collapsed-active after blur: bg `rgba(0,0,0,0)`, icon primary, weight 600, no bar. Recorded treatment: keep this. Bar is leaf language; raised paper is expanded-group language.

Sticky `position`/`zIndex` VERIFIED. Pin-during-scroll on Data UNVERIFIED this session: persisted Funding+Market left only ~52px remaining rail scroll, not enough to reach the sticky constraint.

## IA (not implemented)

D-0010 proposed. Evidence `.eif/audit/NS11_RAIL_20260913/D0010_RAIL_VS_TABS.md`.

## Tests

`pnpm --filter @cip/web exec vitest run src/features/shell/CapabilityRail.test.ts src/features/promotions-funding/FundingChrome.test.ts` — 4 passed.

## Untouched

D-0002, N-0006, N-0013, navConfig hrefs/labels/order, LensTabs, `NAV_STORAGE_GROUP_EXPANDED`, no writes to `cip`.
