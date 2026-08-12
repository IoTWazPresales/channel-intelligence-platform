# Unit 8 — Demo / P2 gate

**Arc:** Q10=A — second-user landing proof + backup/restore soak  
**Branch:** `feat/unit8-demo-p2-gate`  
**Exit:** a second user logs in, sees Control tower, navigates to a surface unaided; restore into disposable DB proven and logged.

Hosting (P2-1) remains deferred.

---

## A. Second-user landing checklist

| # | Check | How | Result |
|---|--------|-----|--------|
| A1 | Admin can open Users | Login `admin@local` → `/admin/users` → create form visible | **PASS** 2026-08-12 — form + `viewer@local` listed |
| A2 | Non-admin account exists | Create or reuse `viewer@local` (role `viewer`) | **PASS** — reused `viewer@local` / Smoke Viewer |
| A3 | Admin can reset password | Users row → Reset password (≥8 chars) | **PASS** — admin API `set-password` → `changeme1` |
| A4 | Logout clears session | Shell logout → `/login` | **PASS** — login form after session switch |
| A5 | Second user lands on Control tower | Login as viewer → `/dashboard` welcome + freshness | **PASS** — Welcome Smoke Viewer; freshness strip |
| A6 | Navigate unaided | Viewer opens one non-admin surface (e.g. Plan vs executed or Shipping) | **PASS** — `/shipping` Inbound shipments loaded |
| A7 | RBAC refuse | Viewer opens `/admin/users` → forbidden / no create form | **PASS** — `users-forbidden` after default-deny fix; API create still 403 |
| A8 | Forgot-password copy | `/login` points to admin Reset password (no SMTP required) | **PASS** — copy visible on login |

**Demo narrative:** `docs/DEMO_SCRIPT.md`

**Code fix this unit:** Users page failed open while `/auth/me` unset; now default-deny + login seeds `auth/me` from login payload.

---

## B. Backup / restore soak

Target **must not** be live `cip`. Default disposable: `cip_alembic_smoke`.

```powershell
# From repo root
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/backup_cip.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/restore_cip_smoke.ps1 `
  -DumpPath .tmp\backups\<file>.dump
```

Expect `RESTORE_SMOKE_OK` with `dim_product` / `import_job` / `alembic` printed.  
Also append a row to `docs/BACKUP_AND_DR.md` proof log.

| # | Check | Result |
|---|--------|--------|
| B1 | `backup_cip.ps1` writes `.tmp/backups/cip_*.dump` | **PASS** — `cip_20260812_124712.dump` (~259 MB) |
| B2 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` prints `RESTORE_SMOKE_OK` | **PASS** |
| B3 | Restored `alembic_version` matches expected head (or note dump lag) | **PASS** — `20260812_0014` |
| B4 | Live `cip` untouched (`current_database` / counts still healthy) | **PASS** — live `dim_product=18177` unchanged |

---

## C. Proof log (executed)

| Date | Check | Evidence |
|------|-------|----------|
| 2026-08-12 | A1–A8 browser | Control tower as Smoke Viewer; Shipping; Users forbidden; login forgot-password copy; admin Users form |
| 2026-08-12 | B1–B4 restore | `RESTORE_SMOKE_OK` → `cip_alembic_smoke`; logged in `docs/BACKUP_AND_DR.md` |

---

## Out of scope

- P2-1 hosting / public URL
- SMTP self-serve reset
- Units 9–10 (094 / 092) — still blocked on inputs
- Re-auditing P5 payment/CN (already smoke PASS on main)
