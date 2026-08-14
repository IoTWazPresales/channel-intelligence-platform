# CURRENT state

**Last updated:** 2026-08-14 (Unit 15B VERIFY PASS)

**Branch:** `feat/unit13-cpor-payment-recon` (from `feat/p5-residual` @ `53361c3`)

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
| **15B** | **VERIFY PASS** — Compute from history + tenant_id fix |
| **15C** | Next — editable promo planner grid (BACKLOG-094 stays open until 15C) |
| P2 hosting | Stay local |
| P6 | Wait for a second company |

Plan: `.tmp/ARC_UNITS_13_15_PLAN.md` · Prompt: `.tmp/unit15_cursor_prompt.md`

## This branch (15A+15B committed)

- 15A: `suggest_intake_weighted_mac`; cover on `commercial_customer_term`; cost-suggest `intake_weighted`; Alembic `20260814_0016` on cip
- 15B: `POST /forecasts/compute-from-history`; `/forecasts` primary CTA; paste/add = override; `tenant_id` never NULL; B1-07 IMPLEMENTED

## Next

1. Live Compute-from-history click on `/forecasts` (this session)
2. **New chat** for Unit 15C — editable promo planner
3. Merge/promote P5+13+14+15 when wanted

**Env:** local Windows. Web `:3000` + API `:8001` (API restarted this session).
