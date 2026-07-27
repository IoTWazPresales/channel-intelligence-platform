# CURRENT state

**Last updated:** 2026-07-27 (On main after promote)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | `28a5e94` (docs pin after promote `30b1525`) |
| **Pushed?** | yes |
| **Next** | Soak; then pick a follow-on (ASUS automap stash / ops-master shell / PM channel_id CASE). |

---

## On main (this promote)

- CPOR historical import + steward Units A–F
- CST E1+E2 (**VERIFY deferred** — not PASS)
- DSI unified multifile + mapping seamlessness clarity
- Shipping commercial KPI contract rebuild
- Alembic **`20260727_0074`**

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.

---

## Parked (not on main from this promote)

- Stash `park-dsi-asus-dealer-name-automap`
- `feat/ops-master-grid-shell-parity` stack
- PM bulk `channel_id` CASE (`558d088`) — verify before cherry-pick
- BACKLOG-078 exclude-sheet UI
