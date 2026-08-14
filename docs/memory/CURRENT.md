# CURRENT state

**Last updated:** 2026-08-14 (Unit 15C committed — promote P5+13+14+15 to main)

**Branch:** `feat/unit13-cpor-payment-recon` (15C commit in progress)

**Alembic on cip:** `20260814_0016` (applied — `commercial_customer_term.target_cover_weeks`)

## Arc progress

| Unit | Status |
|---|---|
| 8 Demo/P2 | **Merged** PR #36 → `main` |
| 11 Import parity | **Merged** PR #37 → `main` (`4aa538a`) |
| 12 P6 light | Export sheet Settings shipped in PR #37 |
| P5 residual | **Pushed** `feat/p5-residual` @ `53361c3` — not yet merged to `main` |
| **13** | **VERIFY PASS** — BACKLOG-092 recon |
| **14** | **VERIFY PASS** — 14A series · 14B widget · 14C ECharts |
| **15A** | **VERIFY PASS** — intake-weighted MAC + per-customer cover |
| **15B** | **VERIFY PASS** + **live Compute** — 26987 velocity + 11466 analogue; 1 override kept |
| **15C** | **VERIFY PASS** — editable promo planner (D-051–D-056). BACKLOG-094 closed |
| P2 hosting | Stay local |
| P6 | Wait for a second company |

Plan: `.tmp/ARC_UNITS_13_15_PLAN.md` · Prompt: `.tmp/unit15c_cursor_prompt.md`

## This branch

- Units 13–15 + P5 residual are on this branch (`origin/main` and `feat/p5-residual` are ancestors)
- 15C: per-line draft + dirty grid + create carries edits + tenant column-mapped export

## Next

1. Push 15C, then merge this branch → `main` (P5 + B1/B4 + Units 13–15)
2. Refresh ROADMAP + close BACKLOG-131/092
3. Browser-smoke B1 / B4 / P5 / dashboards after promote

**Env:** local Windows. Web `:3000` + API `:8001`.
