# N-0114 rendered check (2026-10-23 ~11:00-11:20)

Page: `http://127.0.0.1:3000/design-lab/charts` on the production web build (`vGygvlH5MInZjxZoZ6X8l`, then
`0h3KxTXBgdgBZOwtX4RUz` after the fix below), Chrome via Claude in Chrome. Fixture data only: the design lab
needs no sign-in, and the agent does not sign in to the real app. The real pages listed in the spec section 3
were NOT rendered signed in (sign-in); they use the same components, covered by jsdom tests.

## 1280 x 800 (window 1280 wide; screenshots at the browser's device scale)
- Dark: sections 1-9 checked. Long names wrap to two lines with the full name in `<title>` and the tooltip;
  37 customers flip to horizontal; "Top 10 of 37" caption; axis titles with units (`Outstanding (R)`,
  `Units per week (units)`, `Support spend (US$)`, `Fill rate (%)`, `Weeks of cover`, `Waiting (days)`);
  ticks `R 5 M`, `US$ 45 k`, `14 k`, `86%`; legend only when more than one series (section 8 single
  series has none); pie and donut legends show full names, value and share of the full total.
- Light: same sections, legible; hover cursor visible.
- The single-series last-point label read `5.462` in the screenshot; the DOM text is `5 462`
  (no-break space), so it is the font, not a decimal.

## 390 x 844 (two 390 x 844 iframes of the same page, light and dark; the window itself could not be
## resized below the screen's minimum)
- **Defect found and fixed:** the page was 787 px wide at 390 (horizontal scroll). Cause: the visually
  hidden data table under each chart (a `<table>` ignores `width: 1px`) and Recharts' hidden tooltip box.
  Fix in `features/workbench-ui/charts.tsx` `ChartFigure`: the hidden style sits on a wrapping div and the
  figure clips horizontal overflow. After the rebuild: content width 372 px in a 390 px viewport, light and
  dark, no horizontal scroll.
- Section 1 (37 customers): horizontal, names ellipsised after two lines with the full name on hover;
  toolbar wraps to two rows. Section 5 paired bars: horizontal, legend above. Section 6 pie: legend stacks
  under the pie with full names, value and share.

Tests after the fix: workbench-ui, dashboards, reports, design-lab: 16 files, 121 tests passed; tsc exit 0.
Full web vitest before the fix: 202 files, 1,018 tests passed.
