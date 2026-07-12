# Current state

**Last updated:** 2026-07-12 (Wave 1 finish after Fable CONSULT READY — D1–D5)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see git (Wave 1 finish pending commit) |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |
| **Fable** | CONSULT READY (ops_grid_wave1); VERIFY pending after push |

---

## Wave 1 (ops grid parity — Channel Ops + PVE Apply)

Locked by Fable CONSULT READY:

- Keep premature draft; fix D1–D5 before commit
- No AG Grid this unit (MUI tables + paging)
- Wave 2/3 = separate units after VERIFY PASS

| Item | Status |
|------|--------|
| Page cohort filters ? summary + weekly chart | done |
| Inventory page/page_size + empty UX | done |
| Movements date filters | done |
| Sell-out: single `spec_search` + spec display columns | done (D2) |
| PVE draft From/To/BU + Apply | done |
| D1 BU cohort annotation (`business_unit_applies_to`) | done |
| D3 remove Overview reviewer copy | done |
| D4 Overview summary passes periodGrain/weeks | done |
| D5 CURRENT docs claim corrected | this file |

**FLAG (deferred):** BU filter on derived channel stock / WoC / reporting / customers — needs product?BU join in `sum_derived_channel_stock`.

Audit-gap fixes already at pushed tip `b621a99` (not part of Wave 1 commit).

---

## Next

1. Commit + push Wave 1 ? Fable VERIFY
2. On PASS: Wave 2 (Products filters + CPOR) — separate unit
3. Wave 3: CST empty-state copy
