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
| A5 | Second user lands on Control tower | Login as viewer → `/dashboard` welcome + freshness | **PASS** 2026-08-12; **re-PASS 2026-08-14** — Welcome Smoke Viewer; freshness (newest import 30h) |
| A6 | Navigate unaided | Viewer opens one non-admin surface (e.g. Plan vs executed or Shipping) | **PASS** 2026-08-12 `/shipping`; **re-PASS 2026-08-14** — Inbound shipments 1–50 of 14367; `/plan-vs-executed` fill 13.2% (26Q3) |
| A7 | RBAC refuse | Viewer opens `/admin/users` → forbidden / no create form | **PASS** 2026-08-12; **re-PASS 2026-08-14** — `users-forbidden` “Admin role required to manage users.”; no create form |
| A8 | Forgot-password copy | `/login` points to admin Reset password (no SMTP required) | **PASS** 2026-08-12; **re-PASS 2026-08-14** — copy visible on login |

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
| B1 | `backup_cip.ps1` writes `.tmp/backups/cip_*.dump` | **PASS** 2026-08-12 (~259 MB); **re-PASS 2026-08-14** — `cip_20260814_171118.dump` (~261 MB) |
| B2 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` prints `RESTORE_SMOKE_OK` | **PASS** 2026-08-12; **re-PASS 2026-08-14** |
| B3 | Restored `alembic_version` matches expected head (or note dump lag) | **PASS** 2026-08-12 `20260812_0014`; **re-PASS 2026-08-14** — `20260814_0016` |
| B4 | Live `cip` untouched (`current_database` / counts still healthy) | **PASS** — live `dim_product=18177` unchanged both proofs |

---

## C. Proof log (executed)

| Date | Check | Evidence |
|------|-------|----------|
| 2026-08-12 | A1–A8 browser | Control tower as Smoke Viewer; Shipping; Users forbidden; login forgot-password copy; admin Users form |
| 2026-08-12 | B1–B4 restore | `RESTORE_SMOKE_OK` → `cip_alembic_smoke`; logged in `docs/BACKUP_AND_DR.md` |
| 2026-08-14 | A4–A8 + B1–B4 re-walk | `viewer@local` / `changeme1` → Control tower; Shipping 14367 rows; PvE 13.2%; Users forbidden; restore `20260814_0016` into `cip_alembic_smoke` |

---

## Out of scope

- P2-1 hosting / public URL
- SMTP self-serve reset
- Units 9–10 (094 / 092) — shipped later (Units 13–15); not this gate
- Re-auditing P5 payment/CN (already smoke PASS on main)
