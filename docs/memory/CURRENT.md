# CURRENT state

**Last updated:** 2026-08-04 (BACKLOG-118 PO-link carry + 9→122 + f3)

**Branch:** `main`

**Alembic:** `20260802_0009` · no migration this unit

## Done

- **BACKLOG-118 / D-032:** `soft_supersede_lineup_case` + `carry_case_po_links_on_supersession` (copy-not-move, idempotent, same txn). Wired into `lineup_bulk_backfill_apply` existing-case supersede. Clone `cip_po_carry_smoke` C2–C6 PASS.
- **9→122 on cip:** case 9 superseded; 28/28 PO links copied to 122 (set-diff empty); loser rows preserved; NB 2026 Q2 planned **68881→46830**. Cases **7/90** unchanged. Case count was 34 → then **35** after f3.
- **f3:** targeted preview+apply (session 791, not wholesale 752) with `manual_period_label=2025 Q4` → case **145** NB 2025 Q4, 185 lines, period_source=manual. Q4-only (no month_split — parity with other quarter cases); not uniform_half. Product overlap with case 118 (NB 2025 Q3): **41** shared / 79 vs 76 products — evidence only.

## Next

1. **BACKLOG-119** — residual competition triage (25 multi-BU phantom + 7 cross-period + `PURMIDR26009979`; cases 121/128 still live NB 2026 Q2 with 5 links each).
2. Optional BACKLOG-120 notes-provenance column if steward notes collide.

**Env:** local Windows. `cip`.
