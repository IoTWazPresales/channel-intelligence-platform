# CURRENT state

**Last updated:** 2026-08-02 (lineup corpus restore verified — worker drain + D1–D4)

**Branch:** `main` (ahead of origin)

**Alembic:** `20260802_0009` · no migration this unit

## Done

- P2 corpus-safety `01e55d2`; preview stop `8f38634`.
- Session **752** apply (prior): **30 applied / 5 skipped** — exclusions `f6`,`f13`,`f17`,`f10` (“Do not use”), `f4` (supersession loser of excluded `f6`). **Do not re-apply.**
- Worker drain: `pnpm dev:worker` consumed Redis `batch` 27→0; child jobs **753–779** → 25 completed / 2 failed.
- Post-restore corpus: **cases=33** (30 active), **lines=2450**, **po_links=52**. Survivors **7(22/1), 9(159/28), 90(104/23)** `po_issued` unchanged.
- PF 1H Gaming Desktop → cases **134/135** (2025 Q1+Q2, `half_year_allocation_half` q1/q2). D1 pct evidence: fraction convention; 0 implausible `abs>100`.

## Residual (steward / parked — not this unit)

- Session job **752** still `running` → **BACKLOG-101** (expected).
- Parse failures **759/760** (`2. ACZA 1H 2026 Consumer Lineup - Sales.xlsx`, cases **120/121**, error `could not convert string to float: 'Promo R19999'`).
- **1. ACZA 1H 2026** only case **119** (Q1); Q2 proposal `f4` skipped with exclusion set.
- **355** PO auto-link proposals waiting (links still 52). PvE lineup-linked quarters still **2026 Q1+Q2** only until steward links.
- Preview **needs_attention** 15 (10× `period_signal_conflict`, 4× `slice_row_mapping_failed`, 1× `period_unknown`) — Warren decides in panels.
- **BACKLOG-103** (unified 1H fan-out), **BACKLOG-104** (collision sheet miss) remain open.

## Next

1. Steward: review auto-link proposals + needs_attention period/BU flags; do not “correct” 7/9/90 periods.
2. Decide fate of failed ACZA 1H 2026 file-2 parses (120/121) — re-parse after file fix, not re-apply 752.
3. Optional: BACKLOG-101 terminal status; BACKLOG-104 before next overlapping bulk apply.

**Env:** local Windows. `cip`. Worker may be stopped after drain; Redis `batch` empty.
