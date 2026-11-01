# Dashboard polish — Warren's minimum list (29 Oct 2026)

Taken from Warren's screenshot of the Business dashboard at about 1900 px wide, dark theme. This list is the minimum, not the scope: the session renders every dashboard and widget type and enumerates every issue itself. Presentation only; no number changes.

Status as of 1 Nov 2026. Evidence and before/after pictures: `REPORT.md`.

Layout
1. Every chart fills its widget's height. Today a line chart uses about a quarter of its box when the row is taller (about 550 px empty).
   **FIX done.** Line chart fill 0.41 → 0.72; multi-series 0.37–0.57 (legend and controls take rows; the body scrolls).
2. The canvas fits beside the right-hand panel at every width. Today that panel is clipped ("Ne…", "Pi…").
   **FIX done** (guard in place; the original symptom did not reproduce on the before build). Titles intact beside the canvas at 1920, 1280 and 390.
3. A KPI does not sit alone in a huge empty box. The number is sized to the box, and the KPI's default size is small.
   **FIX done** for the sizing. **BLOCKED** for the default size: I did not find where a new KPI's cell size is chosen; needs a decision on the size.
4. Long category labels wrap or shorten, with the full name on hover and focus. They are never clipped ("AMAZON" shows as "IAZON"). E5 claimed this; find out why it regressed.
   **FIX done** for wrap and hover (bars wrap, tables truncate with the full name on hover). **BLOCKED** for the cause of the regression: not reproduced at 1920, 1280 or 390 on the before build; needs the screen size and data where it showed. Keyboard-focus tooltips on table cells are not verified.

Labels and formatting
5. A KPI shows its unit (lines or units) and its date range.
   **FIX done.** "565 985 units", "All time", data date.
6. Generated titles name every breakdown ("by customer and product"), use no doubled brackets ("Pipeline (inbound) (period)"), and say "period" only when a period breakdown is present.
   **FIX done** (unit-tested; the render board uses explicit titles, so not rendered).
7. Customer and distributor names use CIP's display-name rule, never the legal name in capitals ("AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)").
   **FIX done.**
8. One number format per axis, through the shared formatter. Today one axis mixes "14 k" and "10.5 k" with "7 000".
   **FIX done.** Includes the 100 k–1 M axis ("0 k, 50 k, 100 k").
9. Tables have no blank header column with only a filter icon.
   **FIX done.** Filter buttons hidden in widget tables; numbers right-aligned under their header.
10. The table value column is named after its measure ("Sell-out units"), not "Value".
   **CORRECT AS IS.** The header already names the measure on the before build; the "(units)" suffix is the recorded unit-in-header rule (`table.test.ts`).
11. The dashboard subtitle shows the date range and data freshness, not internal wording ("Unit 14 canvas · governed metrics · not lab fixtures").
   **FIX done.** "Polish board · data as of 2026-11-01"; each widget carries its own range (12).
12. Every widget shows its date range.
   **FIX done.**
13. The column-count control (1 / 2 / 3) has a visible label or tooltip and an accessible name.
   **FIX done.** "Charts per row".

Charts
14. Multi-series charts have a top-N series control (default 5). The series left out are stated (no invented "Other"). Series colours differ in lightness as well as hue.
   **FIX done.** Control added; omitted series stated.
15. Tables sort by the measure, highest first, by default, and have the same top-N control as bar charts.
   **FIX done.**

Found while rendering (not on the list): the Overview page never loaded v2 widgets, and its cards could grow without end once they did. Both fixed; see `REPORT.md`.
