# CURRENT state

**Last updated:** 2026-07-27 (Promoting feat/cpor-listing-status-audit → main)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` (after promote) |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | tip of `feat/cpor-listing-status-audit` @ `da7d491` → merge into main |
| **Pushed?** | feature yes; main promote this session |
| **Next** | Soak on main; deferred: ASUS dealer automap stash; ops-master-grid-shell-parity merge; PM `channel_id` CASE cherry-pick. |

---

## What landed on this promote

- CPOR historical import + steward Units A–F (Unit F layout: `steward*` / `dsi/` / `shipment-evidence/`)
- CST E1+E2 (VERIFY deferred — not PASS)
- DSI unified multifile (batch/coverage/header sniff/file stamps) + mapping seamlessness clarity
- Shipping commercial KPI contract rebuild
- Alembic **`20260727_0074`**

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Steward contract **v1.6**. E1+E2 implemented, VERIFY deferred. A–D PASS; Unit F shipped.

---

## Explicitly not in this promote

- Stash `park-dsi-asus-dealer-name-automap` (still local stash)
- `feat/ops-master-grid-shell-parity` stack (shell on remaining lists, CST alias batch, merge alias seal)
- PM bulk `channel_id` CASE from `558d088` (verify separately)
- BACKLOG-078 exclude-sheet UI
