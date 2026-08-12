# CURRENT state

**Last updated:** 2026-08-12 (Unit 7 BACKLOG-068 landing KPI)

**Branch:** `feat/backlog-068-landed-quarter` (stacked on Unit 5)

**Alembic on cip:** `20260811_0012` (head)

## Arc progress

| Unit | Status |
|---|---|
| 0–3 | Done on main |
| 4 CI | Skipped (Q6=C) |
| 5 CST hist | Pushed `feat/cst-hist-8x4q-game-w27` @ `a562084` — open PR |
| 6 Game W27 | Aliases path; 139 unresolved optional |
| 7 BACKLOG-068 | **Implemented** — Shipping `landed_this_quarter` + shipped-not-landed |
| 8 Demo/P2 | **Next** (Q10=A) |
| 9–10 | Blocked (094 formulas / 092 files) |
| 11 Import parity | Pending (Q13=D) |
| 12 P6 light | Pending (Q14=A) |
| 13 P5 | Last |

## Unit 7

- API: `lineup_quarter_summary` → `landed_this_quarter_units`, `shipped_not_landed_units`
- UI: Shipping lineup quarter strip labels + testids
- Tests: `test_accumulate_landed_this_quarter_vs_plan_landed` (12 passed)
- PvE `fill_rate` untouched

## Next

1. PR Unit 5 then Unit 7 (or stacked PR)
2. Unit 8 demo/P2 gate checklist + backup/restore soak
3. Skip 9–10 until Warren supplies formulas/files
4. Units 11–12; P5 last

**Env:** local Windows. `cip` @ `20260811_0012`.
