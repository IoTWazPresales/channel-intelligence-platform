# Move cip onto the hosted Docker stack

This is the cutover procedure. It does not run the move, start the stack, or change passwords. The database role `PG_OWNER` stays as it is: do not `ALTER` owners and do not assign a new owner.

Do this only after the database queue on the PC has finished, and only if this host is the one live database. After cutover, imports go to this database only. A second live copy will drift.

The database password stays `cip`. A different password needs Warren's OK. Do not edit it in this cutover.

## 1. Final backup on the PC

From the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/backup_cip.ps1
```

The dump is custom format under `.tmp/backups/`. Do not commit it.

If `pg_dump` as `cip` fails because a table is owned by another existing role and `cip` cannot read it, dump as that existing role. Do not change `PG_OWNER` and do not `ALTER TABLE ... OWNER`.

Confirm the dump lists a revision of `20261105_0060` or newer. This checkout's head includes `20261110_0061`. A custom-format dump from a newer Postgres major than the image (`postgres:16`) will not restore. Check `SELECT version();` on the PC before copying.

## 2. Copy the dump

Copy the `.dump` file to the host, outside the repo (for example `/var/backups/cip/`). Do not publish Postgres to do this.

## 3. Restore into the new database

Start Postgres only, so the API does not migrate an empty database before the restore:

```bash
docker compose -f infra/docker/docker-compose.yml up -d postgres
```

Wait until it is healthy. Then print the database name and stop if it is not `cip`:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d cip -tAc "SELECT current_database();"
```

Restore with `--no-owner` so the existing owner role is unchanged and objects load as the database user `cip`:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  pg_restore --no-owner --no-privileges -U cip -d cip - < /path/on/the/host/cip.dump
```

`pg_restore` exit code 1 is warnings. Exit code 2 or higher means stop.

Check:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d cip -tAc "SELECT version_num FROM alembic_version;"
```

The version must be `20261105_0060` or newer. If it is older than the code, start the API afterwards so the entrypoint runs `alembic upgrade head`. If it is newer than this checkout, stop. Do not downgrade.

## 4. Start the stack

Do not expose the host until `infra/docker/docker-compose.yml` has all of the following. The password stays `cip`. Do not invent a new one.

- `CIP_AUTH_MODE: session` on the API, worker and beat (a literal, not a value taken from the shell)
- no host ports for Postgres or Redis
- `restart: unless-stopped` on every service
- listing, mail and summary variables present, defaulting off: `CIP_LISTING_CAPTURE_SCHEDULE`, `CIP_LISTING_LIVE_FETCH`, `CIP_SHIPPING_MAILER_SEND`, `CIP_MAILBOX_IMAP_USER`, `CIP_MAILBOX_IMAP_PASSWORD`, `ANTHROPIC_API_KEY`, `CIP_PUBLIC_WEB_ORIGIN`

The web image in this checkout already listens on `0.0.0.0` inside the container. The Windows start script is unchanged.

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Secrets stay in an uncommitted env file, not in git. Turn listing polls on with `CIP_LISTING_CAPTURE_SCHEDULE=1` and `CIP_LISTING_LIVE_FETCH=1` only when polling should run. Set `CIP_PUBLIC_WEB_ORIGIN` to the URL people open before sending invite mail.

Confirm `GET /login` on port 3000 returns 200, `GET /api/v1/auth/me` with no token returns 401, and nothing is listening on host ports 5432 or 6379.

Then stop imports into the PC database. This host is the only live database.

## 5. Nightly backup and one proven restore

Dump from inside the compose service so the backup does not depend on a published port. Do not change `PG_OWNER`. If `PG_OWNER` is already set and `cip` cannot read a table, use that existing role as `-U`. Otherwise use `cip`.

```bash
mkdir -p /var/backups/cip
stamp=$(date -u +%Y%m%d_%H%M%S)
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  pg_dump -Fc -U cip -d cip > /var/backups/cip/cip_${stamp}.dump
cp /var/backups/cip/cip_${stamp}.dump /mnt/offbox/cip/
```

`/mnt/offbox/cip` is a directory that is not this machine's only disk. Use `scp` when the copy is another machine. Cron, not installed by this repo:

```cron
15 2 * * * cd /opt/cip && stamp=$(date -u +\%Y\%m\%d_\%H\%M\%S) && docker compose -f infra/docker/docker-compose.yml exec -T postgres pg_dump -Fc -U cip -d cip > /var/backups/cip/cip_${stamp}.dump && cp /var/backups/cip/cip_${stamp}.dump /mnt/offbox/cip/
```

Prove restore once into a disposable database, never into `cip`. Print `current_database()` first and stop if it is `cip` or `postgres`.

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d postgres -tAc "SELECT current_database();"
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d postgres -c "CREATE DATABASE cip_restore_smoke OWNER cip;"
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d cip_restore_smoke -tAc "SELECT current_database();"
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  pg_restore --no-owner --no-privileges -U cip -d cip_restore_smoke - \
  < /mnt/offbox/cip/cip_YYYYMMDD_HHMMSS.dump
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U cip -d cip_restore_smoke -tAc "SELECT version_num FROM alembic_version;"
```

The version must be `20261105_0060` or newer. Drop `cip_restore_smoke` by hand when the proof is recorded.
