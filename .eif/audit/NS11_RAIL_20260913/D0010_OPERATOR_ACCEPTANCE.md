# D-0010 accepted — keep rail expansion

**Date:** 2026-09-13  
**Actor:** operator  
**Status:** accepted (Option A)  
**Scope:** N-0023  
**Implementation:** none. Do not collapse the rail, remove tabs, or change nav hrefs/labels/order.

## Operator resolution (verbatim)

Accept A. Keep rail expansion. The two controls are not one destination set — Overview has no tabs, Data has 13 rail leaves against 4 grouped tabs with products/customers/duplicates/CST rail-only, and Funding's tabs include a substrate leaf the rail omits. Only Stock is a true duplicate, which is a Stock-level question not an IA one. Record D-0010 as accepted with that reasoning. Do not implement any IA change.

## Binding terms

1. Rail expansion stays. Live+partial leaves remain in the rail.
2. In-page `LensTabs` stay. They are not the same destination set as the rail.
3. Stock tab/rail duplication is **not** resolved by this decision. It is a Stock-level question, not programme IA.
4. Options B (domains-only rail) and C (remove matching tabs) are **not** accepted.
5. No product implementation is authorised by this recording.

## Evidence that this rests on

`.eif/audit/NS11_RAIL_20260913/D0010_RAIL_VS_TABS.md` (source + Playwright 2026-09-13).
