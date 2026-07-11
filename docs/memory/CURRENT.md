# Current state

**Last updated:** 2026-07-11 (Channel Ops KPI + PM gap scan perf — in progress)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | pending commit |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip |
| **main tip** | `618448c` (PR #7 Theme B merged) |

---

## This branch

- Set-based `sum_derived_channel_stock` / inventory rows (KPI cards were blank while summary N+1 took ~13s)
- PM gap `scan` match-only + proxy undici headersTimeout for `/product-master-gaps/scan`
- Opus CONSULT READY: bug-first queue; parity = CST beachhead then audit matrix (not mega-PR)

---

## Next

1. Restart API so live `:8001` picks up set-based stock.
2. Commit/push this branch; optional PR.
3. Unit 3: CST steward toolbar/filter parity (not shell swap).
4. Unit 4: parity inventory audit (PVE/CPOR/PM gaps/channels/PO/inbound).
5. Deferred: BACKLOG-073; CI pnpm clash.

**Do not re-audit:** U2a/U2b/U-D1/U-G2/U-B2/U-B3a/U-B3b PASSes.
