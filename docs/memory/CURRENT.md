# CURRENT state

**Last updated:** 2026-08-01 (B-lane complete — handover)
**Branch:** `feat/b1-forecasting` @ `176672a` (pushed)
**Alembic:** `20260801_0001` on cip (squash baseline; empty-DB replay proven)

## B-lane tips on this branch

| Unit | Tip |
|------|-----|
| B1-01/02 | `7d6c77f` |
| B1-03 | `098f6d1` |
| B1-04 | `d1f0ea3` |
| B2-01 | `34a5166` |
| B2-02 | `0f43998` |
| B2-03 | `9e4f72e` |
| B4 | `4ab3813` |
| docs tip | `176672a` |

## What works (claims — VERIFY still open)

- Demand forecast SoT: `fact_demand_forecast` (velocity + analogue + manual override)
- Net requirement: `GET /lineup/net-requirement` (dist×product stock subtract)
- Budget dual-track: `GET/POST /lineup/budget-position` (no hard enforce; Q-002 interim)
- Promo draft: `GET /cpor/intelligence/promo-plan-draft`
- Surfaces: `/forecasts`, `/lineup` (B2 panel), `/promotions` (B4 panel), Channel Ops 13w column

## Parked (do not chase unless asked)

- Q-001, Q-002 (reservation column — interim derived), Q-003, Q-009 (PM bias)
- BACKLOG-092 / 093 / 094

## Next

1. Browser VERIFY B-lane (smoke-via-browser rule), or
2. Open PR `feat/b1-forecasting` → `main`, or
3. New lane: P2 / X / parked Qs

**Env:** local Windows — no Docker. API `:8001`, web `:3000`, DB `cip`.
