# CURRENT state

**Last updated:** 2026-08-12 (Unit 8 Demo/P2 gate)

**Branch:** `feat/unit8-demo-p2-gate` (from `main` @ `5f49b7f`)

**Alembic on cip:** `20260812_0014` (matches code head)

## Arc progress

| Unit | Status |
|---|---|
| 0–3 | Done on main |
| 5 CST hist | Merged #30 |
| 7 BACKLOG-068 | Merged |
| P5 payment/CN | Smoke PASS (#35 hotfixes on main) |
| 8 Demo/P2 | **Done this branch** — second-user + backup/restore soak |
| 9–10 | Blocked (094 / 092 full recon) |

## Unit 8 proven

- Browser: `viewer@local` → Control tower → Shipping; `/admin/users` forbidden; admin Users form OK
- Restore: `cip_20260812_124712.dump` → `cip_alembic_smoke` `RESTORE_SMOKE_OK` (alembic `20260812_0014`, dim_product parity)
- Docs: `docs/DEMO_SCRIPT.md`, `docs/UNIT8_DEMO_P2_GATE.md`, `docs/BACKUP_AND_DR.md` proof row
- Fix: Users page default-deny + login seeds `/auth/me` cache

## Next

1. Commit/PR Unit 8 when asked
2. Arc: Unit 11 import parity **or** Unit 12 P6 light **or** P5 residual last (094/092 still blocked)

**Env:** local Windows. API WatchFiles sometimes exits after reload — restart `pnpm dev:api` if :8001 dies.
