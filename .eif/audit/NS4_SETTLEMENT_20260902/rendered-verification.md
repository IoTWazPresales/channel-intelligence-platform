# NS-4 Settlement (N-0008) — implementation rendered verification

**Run:** NS4_SETTLEMENT_IMPL_20260902  
**URL:** http://localhost:3000/commercial-planner/cpor-cases  
**Viewports:** desktop 1280×900, mobile 390×812  
**Actor:** implementation session (not independent review)

## Desktop 1280×900

- Settlement / Book crumb and regime strip render with live totals (Book R 6,021,148.88; Outstanding R 6,021,148.88).
- Scope bar: From/To/BU/Customer structural filters, State combobox (Open · 78), Apply/Reset, Saved view (Settlement desk).
- Book read: shape narrative, portfolio intelligence tiles (support spend, delivery rate, support/unit, cost/incremental unit), top outstanding concentration with `?case=` deep links.
- Queue: 55 open rows, 36px height, settle readiness column, shape bars.
- Case `?case=311` (C26760971): embedded full `CporCaseWorkspace` with Settlement tab selected, FX mode booked/floating, readiness chips, claim upload/rollup, settle case CTA.

## Mobile 390×812

- Mobile nav drawer; scope bar wraps; regime strip stacks.
- Queue and case pane stack vertically; case workspace tabs scroll; settlement panel visible with Settle case button.

## Warm/startup

- Root cause: `formatGridMoney(amount, ccy)` misuse crashed `SettlementRegimeStrip` on first paint (TypeError reading currencyCode).
- Fix: `formatLocalMoney` for book/regime amounts; shared `useSettlementBook` + container prefetch.

## Not verified in this session

- Settle confirm dialog interaction (opened path wired; confirm not executed against live case).
- Independent rendered comparison vs `funding-settlement-r3.html`.
- `design_sameness_review` / `rendered_comparison` gates (await fresh GOV-008 run).
