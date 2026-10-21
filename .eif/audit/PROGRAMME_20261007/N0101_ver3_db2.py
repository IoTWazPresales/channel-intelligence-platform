"""GOV-008 RUN-20261008-N0101-VER3: read-only cip follow-up (continuity after the 21:30 run,
and the live 'failure in between' case). Run from apps/api, venv, PYTHONPATH=. READ ONLY."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings

TZ = "Africa/Johannesburg"


def main() -> None:
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        c.execute(text("SET LOCAL statement_timeout = '60s'"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("transaction_read_only =", c.execute(text("show transaction_read_only")).scalar_one())
        print("now (SAST) =", c.execute(text(f"select now() at time zone '{TZ}'")).scalar_one())
        print(
            "count, min id, max id, gaps, seq last_value =",
            tuple(
                c.execute(
                    text(
                        "select count(*), min(id), max(id), (max(id) - min(id) + 1) - count(*), "
                        "pg_sequence_last_value(pg_get_serial_sequence('listing_observation', 'id')) "
                        "from listing_observation"
                    )
                ).one()
            ),
        )
        print(
            "rows in slot 21:30 SAST: rows, with_snapshot, bytes =",
            tuple(
                c.execute(
                    text(
                        "select count(*), count(raw_snapshot), coalesce(sum(octet_length(raw_snapshot)), 0) "
                        "from listing_observation where fetched_at >= cast('2026-10-08 21:30:00+02' as timestamptz) "
                        "and fetched_at < cast('2026-10-08 22:00:00+02' as timestamptz)"
                    )
                ).one()
            ),
        )
        # Skipped rows whose immediately previous observation (any status, not back-off) was a
        # failure: here "previous of any status" and "previous successful" give different answers.
        rows = c.execute(
            text(
                """
                with s as (
                  select o.id, o.listing_id, (o.parse_flags->>'unchanged_since_observation_id')::bigint as ref
                  from listing_observation o
                  where o.fetched_at >= cast('2026-10-08 15:00:00+02' as timestamptz)
                    and o.parse_flags->>'snapshot_skipped' = 'unchanged'
                )
                select l.marketplace, count(*),
                       count(*) filter (where prev.id <> s.ref)
                from s
                join customer_listing l on l.id = s.listing_id
                join lateral (
                  select p.id, p.http_status, p.parse_status from listing_observation p
                  where p.listing_id = s.listing_id and p.id < s.id and p.parse_status <> 'skipped'
                  order by p.fetched_at desc, p.id desc limit 1
                ) prev on true
                where coalesce(prev.http_status, 0) <> 200 or prev.parse_status <> 'ok'
                group by 1 order by 1
                """
            )
        ).all()
        print("skipped rows right after a failed observation: marketplace, rows, referent != previous-any-status")
        for r in rows:
            print("  ", tuple(r))
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()
