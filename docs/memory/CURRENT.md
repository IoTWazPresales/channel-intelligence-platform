# CURRENT state

**Last updated:** 2026-08-01 (B1-01+02 on cip)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/b1-forecasting` |
| **Alembic** | **`20260801_0001`** (code + cip) |
| **HEAD** | uncommitted |
| **Pushed?** | no |
| **Next** | Commit when asked · B1-03 analogue + override precedence · Opus VERIFY |

---

## B1 progress

| Unit | Status |
|------|--------|
| **B1-01** contract + Alembic squash | Done — empty replay + cip stamp + browser empty then data |
| **B1-02** velocity compute + rollups | Done — ~27k rows on cip; rollups reconcile; UI Method=velocity |
| **B1-03** analogue + overrides | Next |
| **B1-04** polish | Fold if needed |

**Proven:** `/forecasts` grid shows velocity rows (SKU, method, confidence, units).  
`GET /forecasts/rollups?group_by=product|distributor|customer` reconciles to atomic sum.

---

## Standing

Skip payment files / 093/094. Smoke = browser only. Q-001/002/003/009 open.
