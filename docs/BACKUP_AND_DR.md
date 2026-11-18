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
pwsh -File scripts/ops/backup_cip.ps1 -DatabaseUrl "postgresql://<user>:<password>@127.0.0.1:5432/<db>"
```

Defaults:
- URL: none. `-DatabaseUrl` is required; since #97 (`fa962f36`) the script throws `Pass -DatabaseUrl explicitly; there is no default database.` when it is missing.
- Output: `.tmp/backups/cip_YYYYMMDD_HHMMSS.dump`

Never commit `*.dump` files.

## Restore smoke (disposable DB)

Preferred local path when role `cip` lacks `CREATEDB` (common on Windows installs):

```powershell
# 1) Backup
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/backup_cip.ps1 -DatabaseUrl "postgresql://<user>:<password>@127.0.0.1:5432/<db>"

# 2) Restore into an existing disposable DB owned by cip (default: cip_alembic_smoke)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/restore_cip_smoke.ps1 `
  -DumpPath .tmp/backups/<file>.dump `
  -SourceUrl "postgresql://<user>:<password>@127.0.0.1:5432/<source_db>"
```

The script:
1. Requires an explicit `-SourceUrl` and validates both URLs before connecting. Only plain
   `postgresql://` / `postgres://` URLs with one explicit host and one unencoded database path
   are supported. Query parameters are restricted to `sslmode`, `connect_timeout` and
   `application_name`; overrides such as `dbname`, `service`, `host`, `hostaddr`, `port`,
   `user`, `options`, encoded parameter names, and keyword connection strings are refused.
2. Refuses targets `cip`, `cip_test`, `postgres`, `template0`, `template1` and the source
   database, even if the source name looks disposable. Other target names must contain
   `restore`, `smoke`, `scratch` or `disposable`.
3. Reads `current_database()` from both connections and requires each actual identity to match
   its validated URL before wiping. The target identity is independently checked against the
   protected names and source.
4. Drops and recreates the target's public schema, then runs `pg_restore --exit-on-error`.
   Every native command, including identity and verification queries, must exit zero.
5. Checks product/job counts, the Alembic revision and the source product count. Only after
   all checks succeed does it print `RESTORE_SMOKE_OK` and exit zero. A count difference from
   the source is informational because the source may have changed since the dump.

The nightly caller requires **both exit code zero and a complete success marker for its target**.
A failure remains retryable on the next run; a refused target is also written as failed restore
status, so an older successful record cannot hide the refusal.

Optional alternate (needs a role with `CREATEDB`, via env `CIP_PG_ADMIN_URL`): create a fresh DB then restore — keep that for hosting topologies later.

**Do not** point `-TargetUrl` at live `cip`.

## Nightly schedule, retention and restore tests (Wave 3 Phase C)

`scripts/ops/nightly_backup_cip.ps1` runs `backup_cip.ps1`, checks the dump with `pg_restore --list`, prunes old dumps, and every 7 days restores the new dump into a disposable database with `restore_cip_smoke.ps1`.

- **Where:** dumps go to `%LOCALAPPDATA%\CIP\backups\cip_YYYYMMDD_HHMMSS.dump`. The log is `nightly_backup.log` in the same folder.
- **Retention:** the newest 14 daily dumps, plus the newest dump of each of the newest 8 ISO weeks. Only files with that exact name are ever deleted, and the newest dump is always kept. Change this with `-KeepDaily` and `-KeepWeekly`.
- **Failure visibility:**
  - `last_backup.json` and `last_restore.json` in that folder;
  - the exit code, which shows in Task Scheduler's "Last Run Result" (0 means all ok);
  - `/admin/ops`, which shows a Backups card (`GET /admin/ops/overview` `health.backups`). A backup older than 26 hours, or a restore test older than 8 days, shows as stale. A recorded failure shows as failed.
- **Secrets:** the database URLs are read from the user environment variables `CIP_BACKUP_DATABASE_URL` (the database to back up) and `CIP_RESTORE_SMOKE_URL` (a disposable database, never `cip`; the nightly script refuses any target whose database name does not contain `restore`, `smoke`, `scratch` or `disposable`, and always refuses `cip`, `cip_test`, `postgres` and the backed-up database), so no password is written into the task.
- **Plan without changes:** `.\scripts\ops\nightly_backup_cip.ps1 -PlanOnly` prints what it would back up, prune and restore.

One-time operator setup (Warren; not done by agents):

```powershell
[Environment]::SetEnvironmentVariable('CIP_BACKUP_DATABASE_URL', 'postgresql://<user>:<password>@127.0.0.1:5432/cip', 'User')
[Environment]::SetEnvironmentVariable('CIP_RESTORE_SMOKE_URL', 'postgresql://<user>:<password>@127.0.0.1:5432/<disposable db>', 'User')
.\scripts\ops\install_backup_task.ps1            # prints the task
.\scripts\ops\install_backup_task.ps1 -Register  # creates "CIP nightly backup", daily 02:30
```

If the API does not run as the same Windows user, set `CIP_OPS_STATE_DIR` to the folder holding `always-on\` and `backups\`, so `/admin/ops` can read the status files.

## Full restore (destructive — explicit only)

1. Stop API / worker / web writers.
2. `pg_dump` a final safety copy of current `cip`.
3. As superuser: terminate backends → `DROP DATABASE cip` → `CREATE DATABASE cip OWNER cip`.
4. `pg_restore --no-owner --no-privileges -d postgresql://cip:cip@127.0.0.1:5432/cip <dump>`.
5. `alembic current` must match expected head; restart services; smoke login + Control tower.

## Monitoring hooks

- Liveness: `GET http://127.0.0.1:8001/health`
- Readiness: `GET http://127.0.0.1:8001/health/ready` (DB ping)
- Operator UI: `/admin/ops` shows failed import jobs, the readiness chip, and operations health: services from the supervisor's `status.json` (flapping means more than 5 launches in 30 min; a heartbeat older than 180 s is stale), nightly backups and restore tests, and expected weekly reports against the Monday-due rule. Due slots read `pending`; missing current-week tracking or invalid receipt evidence reads `untracked`. The current required period is the prior Mon-Sun week, as in `cst_d1.py`. An older slot cannot stand in for it. `ok` / "Every expected report has arrived" requires valid current-period tracking for every expected customer, no due/late/missing slots, and a newest receipt within the exact preceding 8 days (never in the future). Receipt age is rounded only for display.

## Review regression checks (no database)

- Pester: `Invoke-Pester .\scripts\ops\nightly_backup_cip.Tests.ps1` and
  `Invoke-Pester .\scripts\ops\restore_cip_smoke.Tests.ps1`. The added restore tests mock
  native commands and filesystem probes; they exercise identity mismatches and failures at
  every native step without restoring anything.
- Pytest: `tests/unit/test_ops_health.py` covers missing, pending, untracked and stale/future
  receipts, the exact window boundary, and the endpoint with a mocked session.
- Fix round 1 results: Pester nightly_backup_cip.Tests.ps1 37 passed and restore_cip_smoke.Tests.ps1 17 passed; cip_test 73 passed (ops logs/overview health/unit ops health and config tests); web tsc 0 and vitest administration 18 passed. No real backup, restore, scheduler registration or service restart was run.
- Scheduler installation, authorized real backup/restore proof, database-backed endpoint tests
  on `cip_test`, and browser verification remain required (BACKLOG-247).

## Proof log

| Date | Action | Result |
|------|--------|--------|
| 2026-08-08 | `backup_cip.ps1` → `.tmp/backups/cip_20260808_235826.dump` (~247 MB) | OK |
| 2026-08-08 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` | `RESTORE_SMOKE_OK` dim_product=18177 import_job=257 alembic=`20260807_0010` |
| 2026-08-12 | `backup_cip.ps1` → `.tmp/backups/cip_20260812_124712.dump` (~259 MB) | OK |
| 2026-08-12 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` | `RESTORE_SMOKE_OK` dim_product=18177 import_job=340 alembic=`20260812_0014` (parity with live cip) |
| 2026-08-14 | `backup_cip.ps1` → `.tmp/backups/cip_20260814_171118.dump` (~261 MB) | OK |
| 2026-08-14 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` | `RESTORE_SMOKE_OK` dim_product=18177 import_job=341 alembic=`20260814_0016` (parity with live cip) |
| 2026-09-30 | Readable-table `pg_dump -Fc` as role `cip` after `current_database()=cip` → `.tmp/backups/cip_n0052_exclude_fx.dump` (123 tables, 129,416,904 bytes, dump 62.3s) | OK with a gap: `fx_daily_rate` and `fx_daily_rate_id_seq` omitted. Owner is `postgres`, `cip` has no SELECT, `reltuples=-1`. A GRANT on `cip` was not run. `backup_cip.ps1` still fails on `LOCK TABLE fx_daily_rate`. |
| 2026-09-30 | `restore_cip_smoke.ps1` → `cip_alembic_smoke` (restore 202.7s) | `RESTORE_SMOKE_OK database=cip_alembic_smoke dim_product=18177 import_job=589 alembic=20260906_0022 live_cip_dim_product=18177`. One ignored `pg_restore` error: gist exclusion on `customer_article_alias` because the table-only dump does not recreate extension `btree_gist`. |

The historical 2026-09-30 marker tolerated a restore error. It is not proof under the current
exit-code requirement and must not be used as the first successful scheduled restore.

### N-0052 measured (2026-09-30)

- **RPO:** last successful dump of the tables role `cip` can read. Dump window 62.3s. Target stays "last successful dump before risky ops". This proof is not a full-database dump.
- **RTO:** disposable restore of that dump took 202.7s. That is the data-restore portion. Stopping writers and restarting API/web is still inside the 30–90 min operator target.
- **Parity:** `dim_product` 18177 on the clone equals live `cip` 18177. Clone `import_job` 589, Alembic `20260906_0022`. Live `cip` was not written.

## Out of scope (deferred with hosting)

- Off-box / object-storage backup copies
- Continuous PITR / WAL archiving
- External error trackers (Sentry) — local ops page is the P2-5 bar
