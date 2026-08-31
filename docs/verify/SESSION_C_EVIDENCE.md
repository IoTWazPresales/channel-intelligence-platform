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

---

## 2026-08-31 browser supplement (cursor-ide-browser @ 127.0.0.1:3000)

**Collection timestamp:** 2026-08-31 (Monday), ~10:32 UTC+2  
**Collector:** Cursor agent (SESSION C continuation)  
**Branch:** `feat/ns-1a-fx-readiness-chips`  
**HEAD at collection:** `8f3c10f` (`git rev-parse --short HEAD`)  
**Runbook:** `docs/UNIT8_DEMO_P2_GATE.md`  
**Environment:** local Windows; services via `scripts/restart-dev.ps1`; web `:3000`, API `:8001` warm (`session_d_poll_health.py` → `"database":"cip"`)  
**Credentials:** `admin@local` / `changeme`; `viewer@local` / `changeme1` (after A3 reset)  
**Browser MCP:** `cursor-ide-browser` (origin-gated at `http://127.0.0.1:3000` before interaction)

**Evidence-only. No VERDICT.**

### NS-2 /dashboard supersession flag (A5, A6) — still applies

Gate runbook still targets viewer at `/dashboard` with Control tower naming. NS-2 retires `/dashboard` as north-star landing — **gate rewrite required after NS-2** (supersession rule in runbook).

### A1–A8 (live browser)

| Check | URL path | OBSERVED (2026-08-31) | Blocker / note |
|-------|----------|------------------------|----------------|
| **A1** | `/admin/users` (admin) | Create user form visible (Email, Display name, Temporary password, Role, Create user). | — |
| **A2** | (same) | Tenant table: `admin@local` / Local Admin / admin / yes; `viewer@local` / Smoke Viewer / viewer / yes. | — |
| **A3** | Admin → Users → Reset password | UI uses `window.prompt` for new password — **not automatable** in cursor-ide-browser. | **`PROMPT_DIALOG_UNAUTOMATABLE`**. Ops equivalent on `cip`: stdin Python set `viewer@local` password → `changeme1`, revoke sessions; `current_database(): cip`. |
| **A4** | `/login` after sign out | Login form returned (email/password fields, Sign in). | — |
| **A5** | `/dashboard` (viewer) | Heading **Control tower**; **Welcome , Smoke Viewer**; freshness **Newest successful import: 12d ago (2026-08-18T13:12:11.539572+00:00). Stale after 168 h.** | **`NS-2_GATE_REWRITE`** — run as written; flag for post-NS-2 gate update. |
| **A6** | `/shipping` (viewer) | **Inbound shipments** heading; grid **1–50 of 14724** with data (not loading-only). | **`NS-2_GATE_REWRITE`** — executed at `/shipping` not `/plan-vs-executed`; result recorded. |
| **A7** | `/admin/users` (viewer) | Alert **Admin role required to manage users.** — no create form. | — |
| **A8** | `/login` (logged out) | Verbatim copy: **Forgot password? Ask an admin to use Reset password on Admin → Users.** | — |

### B1–B4 backup/restore (ops scripts)

| Check | OBSERVED (2026-08-31) |
|-------|------------------------|
| **B1** | `backup_cip.ps1` → `.tmp/backups/cip_20260831_103216.dump` (119737682 bytes) |
| **B2–B3** | `restore_cip_smoke.ps1` stdout: `RESTORE_SMOKE_OK database=cip_alembic_smoke dim_product=18177 import_job=279 alembic=20260818_0019 live_cip_dim_product=18177` |
| **B4** | Live `cip` unchanged: `current_database(): cip`; `dim_product=18177` before and after restore |

### Session C — outstanding (evidence gaps, not verdicts)

| Item | Status |
|------|--------|
| A3 UI Reset password click path | Blocked **`PROMPT_DIALOG_UNAUTOMATABLE`** — ops reset documented |
| A5/A6 vs NS-2 landing | Observed as runbook stands; gate rewrite flagged **`NS-2_GATE_REWRITE`** |
| Prior 2026-08-30 partial loads (A5/A6 Loading) | Superseded by 2026-08-31 observations above |

---

*Evidence-only — no VERDICT. For Opus CONSULT.*

