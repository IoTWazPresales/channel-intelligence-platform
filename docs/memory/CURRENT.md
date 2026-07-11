# Current state

**Last updated:** 2026-07-11 (handover — KPI/gap-scan perf shipped; next BACKLOG-074)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | `4a4f1ed` |
| **PR** | Not opened — open when Warren says |
| **Alembic (DB)** | **`20260710_0072`** on cip |
| **main tip** | `618448c` (PR #7 Theme B merged) |

---

## Shipped on this branch (unproven live until API restart)

- Set-based `sum_derived_channel_stock` — summary ~13s ? ~2.1s in-process; KPI cards were blank while loading
- PM gap `scan` match-only — ~318s ? ~1.3s; Next proxy undici long Agent for `/product-master-gaps/scan`
- BACKLOG-074 parked (grid chrome parity program); Opus queue: CST beachhead ? audit matrix

---

## Next

1. **Restart API** (`pnpm dev:api`) so `:8001` picks up set-based stock; confirm Channel Ops cards paint.
2. Open PR for this branch ? merge when ready.
3. **BACKLOG-074 Unit 3:** CST steward toolbar/filter parity (capability parity — do **not** swap onto MasterDataGridShell).
4. Unit 4: parity inventory audit (PVE / CPOR / PM gaps / channels / PO / inbound) — docs matrix, then Warren picks.
5. Deferred: BACKLOG-073; CI pnpm Action version clash.

**Do not re-audit:** U2a/U2b/U-D1/U-G2/U-B2/U-B3a/U-B3b PASSes · Theme B PR #7.
