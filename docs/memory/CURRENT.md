# CURRENT state

**Last updated:** 2026-08-14 (promoted P5 + Units 13–15 → `main`; post-promote browser smoke)

**Branch:** `main` @ `e4cc143` (plus this pin)

**Alembic on cip:** `20260814_0016` (applied — do not upgrade further unless approved)

## On main

| Unit | Status |
|---|---|
| 8 / 11 / 12 | Merged PRs #36 / #37 |
| **P5 residual** | On `main` — Takealot REST + activation. Browser: Observations `price_consistent` vs C26759823 |
| **13** | VERIFY PASS + browser Payments/Recon on case 312. BACKLOG-092 closed |
| **14** | VERIFY PASS + browser canvas (3 widgets, formula + vintage). BACKLOG-131 closed |
| **15A–C** | VERIFY PASS + browser B1 Compute CTA / B4 2-line draft. BACKLOG-094 closed |
| P2 hosting | Stay local (Q-003) |
| P6 | Wait for a second company |

## Post-promote browser (local `:3000` / `:8001`)

- `/forecasts`: Compute from history, Add/Paste override, 21 rows. Did **not** click Compute.
- `/promotions`: seed 27 → 2 lines; MAC popover display legs + `dsi_wac_not_ingested`.
- `/dashboards`: Unit 14 canvas, 3 charts, formula + vintage on face.
- `/listing-capture` Observations: Takealot 200/ok; `price_consistent` and `no_case_detected`. Guide: not intelligence v1. Did **not** poll.
- CPOR Cases list recon copy + case 312 Payments/Recon panel.
- Admin Users: Reset password (local bar). Login: no self-serve email reset.

## Next

Remaining: P2 unaided second-user landing + restore proof; P3-1 / beat soak; P4 residuals; P5 intelligence v1; P6 second tenant; Lane X TRIGGER items.

**Env:** local Windows. Web `:3000` + API `:8001`.
