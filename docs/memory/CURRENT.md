# CURRENT state

**Last updated:** 2026-08-03 (commercial parse month grain + 1H month-derived)

**Branch:** `main` (ahead of origin)

**Alembic:** `20260802_0009` · no migration this unit

## Done

- **D-028:** commercial `lineup_case_parser` writes `month_split_json`; 1H halves derive qty from real months; refuse when months absent (`half_year_split_requires_month_columns`); `uniform_half` unreachable from parse; Promo bare-float hardened.
- Re-parsed on cip (no 752 re-apply): **114, 115, 116, 119, 120, 121, 134, 135**. Cases **120/121** now have lines (201 each). `case_po` still **52**. Survivors **7/9/90** unchanged.
- Sample 114 row1: q1 `quantity_units=72` / `month_split={Feb:72}` (not ceil(144/2) fabrication — month-derived).

## Residual

- **BACKLOG-105** PF `Qty`≈0.15 vs `Total Qty` / month columns (not fixed).
- **BACKLOG-101/103/104** still open; session 752 still `running`.
- Missing archive gaps from §6 remain (NB Q4 2025 needs_attention; 1H-2026 file-1 Q2 excluded).

## Next

1. Steward: auto-link proposals + remaining needs_attention.
2. Optional: BACKLOG-105 PF Qty mapping; BACKLOG-104 before next overlapping bulk apply.

**Env:** local Windows. `cip`.
