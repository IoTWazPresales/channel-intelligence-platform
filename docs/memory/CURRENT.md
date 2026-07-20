# CURRENT state

**Last updated:** 2026-07-20 (CPOR H1 historical import backbone)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **HEAD** | (pending commit) CPOR H1 historical import |
| **Alembic (DB)** | **`20260710_0072`** on cip ? code head adds **`20260720_0073` NOT applied** |
| **Next** | Warren: smoke/apply `0073` on cip ? **H2** steward + async apply |

---

## CPOR historical import (in flight)

- Fable CONSULT READY: both Disti+Reseller sheets; frozen Result snapshot; tenant mapping profile; shared steward in H2
- **H1 shipped (code):** parser/validate/profile + staging/origin migration authored
- Real workbook smoke: ~17.3k rows / ~1.1k cases parse+validate OK (no DB write)
- **Do not** apply 0073 without Warren

---

## Parked ? DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`
- Resume TRIGGER: Warren asks to finish job 553 steward/apply

---

## Do not

- Push main; alembic without approval; auto-create dims; invent waterfall rewrite of settled Results
