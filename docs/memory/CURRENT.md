# CURRENT state

**Last updated:** 2026-08-01 (Q-001/002/009 resolved — tenant profile)
**Branch:** `feat/b1-forecasting`
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

## What works

- Demand forecast SoT + B-lane surfaces (browser VERIFY PASS 2026-08-01)
- Tenant commercial profile stub (`commercial_tenant_profile.py`): money ceiling, derived-from-profit reservation, PM=business_line
- Q-001 / Q-002 / Q-009 **Resolved**; Q-003 hosting still open

## Parked

- Q-003 hosting · BACKLOG-092 / 093 / 094 · over-money reapproval + profile onboarding UI (new BACKLOG)

## Next

1. Commit Channel Ops VERIFY fixes (if still dirty) + this Q-resolve unit
2. BACKLOG reapproval / onboarding when TRIGGER fires
3. PR → main or P2/X when Warren picks

**Env:** local Windows — no Docker. API `:8001`, web `:3000`, DB `cip`.
