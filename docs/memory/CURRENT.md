# CURRENT state

**Last updated:** 2026-08-12 (Unit 5 stats re-verified on cip)

**Branch:** `feat/cst-hist-8x4q-game-w27` (dirty — **0 commits** ahead of `main` @ `debf1f8`)

**Alembic on cip:** `20260811_0012` (head)

## Arc progress

| Unit | Status |
|---|---|
| 0–3 | Done on main |
| 5 CST hist + Game W27 | Code+data on cip; **uncommitted** on branch |
| 7–12 | Pending |
| 13 P5 | Last |

## Verified on cip (2026-08-12)

### Aliases
| Metric | Count |
|---|---:|
| Confirmed | **590** (was ~533 unique SCM + shipping eras) |
| Proposed | **62** |
| Confirmed open-ended (no window) | 537 |
| Confirmed with `valid_from`+`valid_to` | 27 |

### Game W27 (jobs 928 / 971)
Staging **565** · resolved **426** · unresolved **139** · **6** period grains. Fact rows for Game total **38** (upsert grain ≠ staging rows).

### Fact totals (all periods) vs Unit 5 window (2025Q3–2026Q2)

| Customer | All facts / periods | In-window Q coverage |
|---|---:|---|
| Takealot | 96 / 5 | **4/4** (76 facts in window) |
| Computer Mania | 302 / 5 | **4/4** (246 in window) |
| Makro | 362 / 30 | **4/4** (pivoted multi-week) |
| Evetech | 130 / 4 | **3/4** — no Q3 EveX Sales in RAW |
| Game | 38 / 10 | **3/4** — Q4 Week 48 landed as `2026-11-23` (year mis-stamp), **0 facts in 2025Q4** |
| Hifi / IC | 51 / 1 · 82 / 1 | **0/4** — P4 WK24 only (`2025-06-09`); Pepkor Combined RAW ends WK26/Q2 |
| Amazon | **0** | **0/4** — RAW Sales extracts truncated |

**RAW gaps (not code bugs):** Amazon Sales_*; Pepkor Combined Chain after WK26; Evetech Q3 EveX Sales; Game Q4 needs re-ingest with year=2025.

## Next

1. **Commit/PR** dated-alias migration+code+tests (Warren ask) — branch has no commits yet
2. Optional: fix Game Q4 period stamp + re-apply Week 48; steward 139 unresolved
3. Arc **Units 7+**; **P5 last**
4. Blocked: 094 formulas; 092 payment files

**Env:** local Windows. `cip` @ `20260811_0012`.
