# Dashboard polish — Warren's minimum list (29 Oct 2026)

Taken from Warren's screenshot of the Business dashboard at about 1900 px wide, dark theme. This list is the minimum, not the scope: the session renders every dashboard and widget type and enumerates every issue itself. Presentation only; no number changes.

Layout
1. Every chart fills its widget's height. Today a line chart uses about a quarter of its box when the row is taller (about 550 px empty).
2. The canvas fits beside the right-hand panel at every width. Today that panel is clipped ("Ne…", "Pi…").
3. A KPI does not sit alone in a huge empty box. The number is sized to the box, and the KPI's default size is small.
4. Long category labels wrap or shorten, with the full name on hover and focus. They are never clipped ("AMAZON" shows as "IAZON"). E5 claimed this; find out why it regressed.

Labels and formatting
5. A KPI shows its unit (lines or units) and its date range.
6. Generated titles name every breakdown ("by customer and product"), use no doubled brackets ("Pipeline (inbound) (period)"), and say "period" only when a period breakdown is present.
7. Customer and distributor names use CIP's display-name rule, never the legal name in capitals ("AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)").
8. One number format per axis, through the shared formatter. Today one axis mixes "14 k" and "10.5 k" with "7 000".
9. Tables have no blank header column with only a filter icon.
10. The table value column is named after its measure ("Sell-out units"), not "Value".
11. The dashboard subtitle shows the date range and data freshness, not internal wording ("Unit 14 canvas · governed metrics · not lab fixtures").
12. Every widget shows its date range.
13. The column-count control (1 / 2 / 3) has a visible label or tooltip and an accessible name.

Charts
14. Multi-series charts have a top-N series control (default 5). The series left out are stated (no invented "Other"). Series colours differ in lightness as well as hue.
15. Tables sort by the measure, highest first, by default, and have the same top-N control as bar charts.
