# CURRENT state

**Last updated:** 2026-08-14 (P2 local exit re-proven; leftover holes that cannot close named)

**Branch:** `feat/close-remaining-holes` (docs) off `main` @ `f251bcc`

**Alembic on cip:** `20260814_0016` (applied — do not upgrade further unless approved)

## On main

| Unit | Status |
|---|---|
| 8 / 11 / 12 | Merged PRs #36 / #37 |
| **P2 local** | **Proven live 2026-08-14** — `viewer@local` Control tower → Shipping / PvE; Users forbidden; restore `cip_alembic_smoke` alembic `20260814_0016` |
| **P5 residual** | On `main` — Takealot REST + activation. Browser: Observations `price_consistent` vs C26759823 |
| **13** | VERIFY PASS + browser Payments/Recon on case 312. BACKLOG-092 closed |
| **14** | VERIFY PASS + browser canvas (3 widgets, formula + vintage). BACKLOG-131 closed |
| **15A–C** | VERIFY PASS + browser B1 Compute CTA / B4 2-line draft. BACKLOG-094 closed |
| P2 hosting | Stay local (Q-003) |
| P6 | Wait for a second company |

## Proven this session (local `:3000` / `:8001`)

- Viewer `viewer@local` / `changeme1`: Control tower (Smoke Viewer, freshness 30h); Shipping 1–50 of 14367; PvE fill **13.2%** (26Q3); `/admin/users` `users-forbidden`.
- Restore: dump `cip_20260814_171118.dump` (~261 MB) → `cip_alembic_smoke` `RESTORE_SMOKE_OK` dim_product=18177 import_job=341 alembic=`20260814_0016` (live cip count unchanged).
- `/lineup` Export XLSX (`lineup-net-requirement-export-xlsx`) visible; did **not** click Apply / Clear.
- `/reports` Run + **Send to inbox** → delivery **#4** `sellout_units` 178261.85; `/inbox` 4 items with vintage on face.
- P3-5 **unattended Monday 07:00** not proven (needs `CIP_ENABLE_DEV_BEAT=1` overnight).

## Next (new units — not closable as housekeeping)

- **P3-1** tenant-defined metrics without a deploy (CONSULT first).
- **P5 intelligence v1** after ≥2 weeks promo-activated vs not observations.
- **P6** second tenant (needs a real second company).
- Lane X: BACKLOG-076 / 089 / 079 residual fold-in when those pages are next edited.
- P4 soak residuals: Amazon ASIN FLAG, optional Game W27, historical CST backfill (explicit ask).

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
