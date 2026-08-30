# SESSION C Evidence - Unit 8 Demo / P2 gate

**Collection timestamp:** 2026-08-30 (Sunday), ~21:30 UTC+2  
**Collector:** Cursor agent (command execution subagent)  
**Branch:** feat/ns-1a-fx-readiness-chips  
**HEAD at collection:** 159b838  
**Runbook:** docs/UNIT8_DEMO_P2_GATE.md  
**Environment:** local Windows; web port 3000, API port 8001 (API down on first Playwright attempt; started pnpm dev:api before pass)  
**Credentials:** admin@local / changeme; viewer@local / changeme1  

**Evidence-only for Opus CONSULT VERIFY. No PASS/FAIL verdicts.**

---

## NS-2 /dashboard supersession flag (A5, A6)

North-star nav (NS-2) treats /dashboard as landing absorbing legacy Control tower naming. Unit 8 still expects viewer at /dashboard with welcome and freshness.

**OBSERVED viewer /dashboard:** Overview breadcrumb; heading Control tower; body still showed Loading at snapshot (welcome/freshness KPIs not fully painted).

**OBSERVED viewer /shipping:** Inbound shipments heading and filters; grid showed 0-0 of 0 and Loading data at snapshot.

---

## A1-A8 (Playwright live, apps/web)

| Check | URL path | Observed |
|-------|----------|----------|
| A1 | /admin/users | Create user form; tenant table lists admin@local and viewer@local |
| A2 | (same) | viewer@local Smoke Viewer role viewer active yes |
| A3 | - | NOT RUN (no reset-password action) |
| A4 | /login after logout | Login form returned |
| A5 | /dashboard | Control tower heading; Loading partial (see NS-2 flag) |
| A6 | /shipping | Inbound shipments chrome; grid loading at capture |
| A7 | /admin/users | Admin role required to manage users; no create form |
| A8 | /login | Forgot password copy points to Admin Users Reset password |

First Playwright attempt: login alert Request failed (500) with API stopped. Screenshots under apps/web/test-results/session-c/ (gitignored).

---

## B1-B4 backup/restore

**B1** backup_cip.ps1 -> .tmp/backups/cip_20260830_211714.dump (119737174 bytes)

**B2-B4** restore_cip_smoke.ps1 output:

RESTORE_SMOKE_OK database=cip_alembic_smoke dim_product=18177 import_job=277 alembic=20260818_0019 live_cip_dim_product=18177

