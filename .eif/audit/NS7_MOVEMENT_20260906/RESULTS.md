# Movement lens week-key defect

## Classification (NUMBER RULE)

**(ii) computation bug.** Old headlines were wrong. New headlines match ISO-week SQL on `cip`.

`current_database()=cip`
`timezone=Africa/Johannesburg`

| Figure | Old (date_trunc timestamptz → Python `.date()` Sunday) | SQL truth (ISO Monday) | New |
|---|---|---|---|
| Sell-out W24 | 0 | 1119 | 1119 |
| Prior week W23 | (lookup miss) | 2095 | 2095 |
| WoW | null | (1119−2095)/2095 = −46.6% | −46.6% |
| Families growing | 0 of 8 | NR only → 1 of 8 | 1 of 8 |
| Shipped W35 | 1477 | 1477 | 1477 (unchanged) |
| Network SOH | 64121.2 | 64121.2 | 64121.2 (unchanged) |

Root cause: `date_trunc('week', transaction_date)` returns `timestamptz` Sunday 22:00 UTC (Monday 00:00 SAST). Python `.date()` is Sunday. Movement zero-filled against Python Mondays, so every week including W24 looked up as 0. Nested `/weekly-series` plotted the truncated buckets’ **units** directly, so the bar was ~1119.

## Fix

`_iso_week_start_expr`: `CAST(col AS date) - EXTRACT(ISODOW) + 1` (Monday as `date`). Used by movement-lens, weekly-series, and cover weekly_flow. `_week_monday` snaps leftover timestamptz to SAST before `.date()`.

## Browser

`http://localhost:3000/stock?lens=movement` after API restart. Lab strip: Sell-out W24 **1 119**, −46.6% vs prior week, Families **1 of 8**, Shipped W35 **1 477**, Network SOH **64 121**. Nested “Sell-out by week” still ~1119. CDP `Emulation.setDeviceMetricsOverride` denied (`BROWSER_UNSAFE`); layout is desktop rail (not 390). Playwright `setViewportSize(1280,800)` ran on a separate Playwright session.

## Tests

`pytest tests/test_channel_ops_api.py` — 12 passed (mocked; no cip writes).
