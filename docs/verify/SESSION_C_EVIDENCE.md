# SESSION C — Unit 8 Demo/P2 Gate Evidence

**Run ID:** SESSION-C-20260830-2100  
**Timestamp (UTC):** 2026-08-30T19:00:00Z  
**Branch:** `feat/ns-1a-fx-readiness-chips`  
**Commit:** `159b838` (`git rev-parse --short HEAD` at collection)  
**Services:** web `http://localhost:3000` · API `http://localhost:8001` (ports confirmed via `Test-NetConnection` in prior restart)  
**Gate reference:** `docs/UNIT8_DEMO_P2_GATE.md`  
**Executor:** Cursor VERIFY evidence session (parent + shell subagents)

**Evidence only — no PASS/FAIL verdicts.**

---

## NS-2 supersession flags (per runbook)

| Check | Gate text | NS-2 note |
|-------|-----------|-----------|
| **A5** | viewer login → `/dashboard` | **FLAG:** NS-2 retires `/dashboard`. Gate step must be rewritten post–NS-2; this session records gate-as-written only. |
| **A6** | viewer navigates unaided to non-admin surface | **FLAG:** If gate implies landing on `/dashboard`, NS-2 supersedes that path; record actual post-login route when re-run. |

---

## Collection blocker (material)

**OBSERVED:** EIF pre-tool hook `.cursor/hooks/eif_guard.cmd` failed closed on Shell, browser MCP (`cursor-ide-browser`, `user-playwright`), and most follow-up automation in parent agent and one shell subagent turn.

**OBSERVED:** One Playwright navigate to `/login` succeeded (title "Channel Intelligence"); subsequent snapshot/click blocked.

**Consequence:** A1–A8 browser journey and B1–B4 ops scripts **not executed with verbatim output in this SESSION C file** during the blocked subagent turn. Re-run required with EIF guard grants for shell + browser.

---

## A1 — admin@local → /admin/users create form

| Field | Value |
|-------|-------|
| **Attempted** | No (browser blocked after login page load) |
| **Observed** | BLOCKED |
| **Expected** | Admin Users page with create-user form visible |

---

## A2 — viewer@local exists

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED — requires A1 or DB/API query |
| **Expected** | `viewer@local` (role `viewer`) present in user list |

---

## A3 — admin reset password

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED |
| **Expected** | Admin can reset viewer password (≥8 chars) |

---

## A4 — logout → /login

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED |
| **Expected** | Logout returns to `/login` |

---

## A5 — viewer login → /dashboard

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED |
| **Credentials (gate):** | `viewer@local` / `changeme1` (per UNIT8 doc; not verified this session) |
| **Expected (gate-as-written):** | Post-login URL `/dashboard` with welcome + freshness |
| **NS-2 FLAG** | Gate references `/dashboard`; NS-2 retires this route — rewrite gate after NS-2 merge |

---

## A6 — viewer navigates unaided

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED |
| **NS-2 FLAG** | Depends on post-login landing; do not treat `/dashboard` as canonical after NS-2 |
| **Expected** | Viewer opens non-admin surface (e.g. Shipping, Plan vs executed) without admin help |

---

## A7 — viewer /admin/users → forbidden

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED |
| **Expected** | Forbidden message; no create form |

---

## A8 — forgot-password copy on /login

| Field | Value |
|-------|-------|
| **Attempted** | Partial |
| **Observed** | `browser_navigate` → `http://localhost:3000/login` succeeded once; page title **Channel Intelligence** |
| **Forgot-password copy** | NOT CAPTURED — snapshot blocked after navigate |
| **Expected** | Login page copy points to admin Reset password (no SMTP) |

---

## B1 — backup_cip.ps1 → .tmp/backups/cip_*.dump

| Field | Value |
|-------|-------|
| **Command** | `scripts/ops/backup_cip.ps1` |
| **Attempted** | No |
| **Observed** | BLOCKED — Shell denied in subagent turn |
| **Expected** | `.tmp/backups/cip_YYYYMMDD_HHMMSS.dump` created |

---

## B2 — restore_cip_smoke.ps1 → cip_alembic_smoke

| Field | Value |
|-------|-------|
| **Command** | `scripts/ops/restore_cip_smoke.ps1 -DumpPath .tmp\backups\<latest>.dump` |
| **Target DB** | `cip_alembic_smoke` only (NOT `cip`) |
| **Expected marker** | `RESTORE_SMOKE_OK` |
| **Attempted** | No |
| **Observed** | BLOCKED |

---

## B3 — alembic_version on restored DB

| Field | Value |
|-------|-------|
| **Target** | `cip_alembic_smoke` |
| **Attempted** | No |
| **Observed** | BLOCKED — depends on B2 |
| **Expected** | `alembic_version` matches code head or documented dump lag |

---

## B4 — live cip untouched

| Field | Value |
|-------|-------|
| **Attempted** | No |
| **Observed** | BLOCKED — no before/after `dim_product` count |
| **Expected** | `current_database() = cip`; row counts unchanged after B2 |

---

## Prior proof (historical — not this session OBSERVED)

From `docs/UNIT8_DEMO_P2_GATE.md` §C (2026-08-12 / 2026-08-14 re-walk): A1–A8 browser PASS and B1–B4 `RESTORE_SMOKE_OK` into `cip_alembic_smoke`. **Out of scope** for this SESSION C OBSERVED column — listed for consultant context only.

---

## Outstanding

1. Re-run A1–A8 with authenticated browser after EIF guard unblocks MCP.
2. Re-run B1–B4 ops scripts; capture `RESTORE_SMOKE_OK` and `alembic_version` verbatim.
3. Rewrite A5/A6 in `UNIT8_DEMO_P2_GATE.md` after NS-2 lands (post-login route no longer `/dashboard`).

---

*Evidence-only — no VERDICT. For Opus CONSULT.*
