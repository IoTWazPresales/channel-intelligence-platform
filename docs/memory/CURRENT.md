# CURRENT state

**Last updated:** 2026-08-12 (payment evidence smoke + widen CN id)

**Branch:** `main` (post #32–#34; smoke hotfixes pending merge)

**Alembic on cip:** `20260812_0014` (matches code head)

## Arc progress

| Unit | Status |
|---|---|
| 0–3 | Done on main |
| 5 CST hist | Merged #30 |
| 7 BACKLOG-068 | Merged (`0cf0c6c`) |
| P5 payment/CN | **Smoke PASS** — Cases shell, Ken validate 3375 rows, apply 3375 evidence, Payments tab |
| 8 Demo/P2 | **Next** |
| 9–10 | Blocked (094 / 092 full recon) |

## Smoke proven (browser)

- Cases `MasterDataGridShell` loads (N+1 fix #34)
- Import payment/CN: profile `asus_cpor_pending_report_v1`; job #977 → 3375 rows / 2544 cases / 283 linked
- Apply upserted 3375 `cpor_payment_evidence` (shells 0 — none marked)
- Case `C26649381` Payments tab shows CN rows (evidence-only case status)

## Next

1. Merge smoke hotfixes (admin sources header, CN VARCHAR 512, ensure race)
2. Unit 8 Demo/P2 gate

**Env:** local Windows. API WatchFiles sometimes exits after reload — restart `pnpm dev:api` if :8001 dies.
