# Backup and disaster recovery (local P2-5)

**Scope:** local Windows / topology B (Postgres on `localhost:5432`, database `cip`).
Hosting / cloud DR remains deferred with P2-1 until a hosting target is set.

## Objectives

| Item | Local target |
|---|---|
| **RPO** | Last successful `pg_dump` (aim: daily before risky ops / migrations) |
| **RTO** | Recreate DB + restore dump + restart API/web (~30–90 min depending on dump size) |
| **Proof** | At least one restore into a disposable DB (`cip_restore_smoke`) has been run |

## Backup (dump)

```powershell
# From repo root — writes custom-format dump under .tmp/ (gitignored)
pwsh -File scripts/ops/backup_cip.ps1
```

Defaults:
- URL: `postgresql://cip:cip@127.0.0.1:5432/cip`
- Output: `.tmp/backups/cip_YYYYMMDD_HHMMSS.dump`

Never commit `*.dump` files.

## Restore smoke (disposable DB)

Preferred local path when role `cip` lacks `CREATEDB` (common on Windows installs):

```powershell
# 1) Backup
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/backup_cip.ps1

# 2) Restore into an existing disposable DB owned by cip (default: cip_alembic_smoke)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/restore_cip_smoke.ps1 `
  -DumpPath .tmp/backups/<file>.dump
```

The script:
1. Refuses target `cip` / `postgres`
2. `DROP SCHEMA public CASCADE` + recreate on the target disposable DB
3. `pg_restore` into that DB
4. Prints `dim_product` / `import_job` / `alembic_version` counts

Optional alternate (needs a role with `CREATEDB`, via env `CIP_PG_ADMIN_URL`): create a fresh DB then restore — keep that for hosting topologies later.

**Do not** point `-TargetUrl` at live `cip`.

## Full restore (destructive — explicit only)

1. Stop API / worker / web writers.
2. `pg_dump` a final safety copy of current `cip`.
3. As superuser: terminate backends → `DROP DATABASE cip` → `CREATE DATABASE cip OWNER cip`.
4. `pg_restore --no-owner --no-privileges -d postgresql://cip:cip@127.0.0.1:5432/cip <dump>`.
5. `alembic current` must match expected head; restart services; smoke login + Control tower.

## Monitoring hooks

- Liveness: `GET http://localhost:8001/health`
- Readiness: `GET http://localhost:8001/health/ready` (DB ping)
- Operator UI: `/admin/ops` — failed import jobs + readiness chip

## Proof log

| Date | Action | Result |
|------|--------|--------|
| 2026-08-08 | `backup_cip.ps1` → `.tmp/backups/cip_20260808_235826.dump` (~247 MB) | OK |
| 2026-08-08 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` | `RESTORE_SMOKE_OK` dim_product=18177 import_job=257 alembic=`20260807_0010` |
| 2026-08-12 | `backup_cip.ps1` → `.tmp/backups/cip_20260812_124712.dump` (~259 MB) | OK |
| 2026-08-12 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` | `RESTORE_SMOKE_OK` dim_product=18177 import_job=340 alembic=`20260812_0014` (parity with live cip) |

## Out of scope (deferred with hosting)

- Off-box / object-storage backup copies
- Continuous PITR / WAL archiving
- External error trackers (Sentry) — local ops page is the P2-5 bar
