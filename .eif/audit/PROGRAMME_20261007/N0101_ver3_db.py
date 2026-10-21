"""GOV-008 RUN-20261008-N0101-VER3: read-only cip probe for the round 3 snapshot policy.

Run from apps/api with its virtualenv (PYTHONPATH=.). READ ONLY: SET TRANSACTION READ ONLY,
statement_timeout 60s, rolled back. Prints no URL, host, user or secret.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings

TZ = "Africa/Johannesburg"
SINCE_BASE = "2026-10-08 13:00:00+02"  # round 2 worker afternoon baseline
SINCE_R3 = "2026-10-08 15:00:00+02"


def q(c, sql, **p):
    return c.execute(text(sql), p).all()


def show(title, rows):
    print(f"\n## {title}")
    for r in rows:
        print("  ", tuple(r))


def main() -> None:
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        c.execute(text("SET LOCAL statement_timeout = '60s'"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("transaction_read_only =", c.execute(text("show transaction_read_only")).scalar_one())
        print("now (SAST) =", c.execute(text(f"select now() at time zone '{TZ}'")).scalar_one())

        slot = (
            f"date_trunc('hour', o.fetched_at at time zone '{TZ}') + "
            f"(floor(extract(minute from o.fetched_at at time zone '{TZ}') / 30) * interval '30 min')"
        )
        show(
            "per 30-min slot since 13:00: slot, rows, with_snapshot, without, snapshot_bytes",
            q(
                c,
                f"""
                select {slot} as s, count(*), count(o.raw_snapshot), count(*) - count(o.raw_snapshot),
                       coalesce(sum(octet_length(o.raw_snapshot)), 0)
                from listing_observation o
                where o.fetched_at >= cast(:since as timestamptz)
                group by 1 order by 1
                """,
                since=SINCE_BASE,
            ),
        )
        show(
            "per slot x marketplace since 15:00: slot, marketplace, rows, with_snapshot, bytes",
            q(
                c,
                f"""
                select {slot} as s, l.marketplace, count(*), count(o.raw_snapshot),
                       coalesce(sum(octet_length(o.raw_snapshot)), 0)
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.fetched_at >= cast(:since as timestamptz)
                group by 1, 2 order by 1, 2
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "since 15:00 by marketplace: marketplace, rows, with_snapshot, bytes",
            q(
                c,
                """
                select l.marketplace, count(*), count(o.raw_snapshot),
                       coalesce(sum(octet_length(o.raw_snapshot)), 0)
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.fetched_at >= cast(:since as timestamptz)
                group by 1 order by 1
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "since 15:00 by marketplace x policy flag: marketplace, stored, skipped, http, parse, rows, with_snapshot, bytes",
            q(
                c,
                """
                select l.marketplace, o.parse_flags->>'snapshot_stored', o.parse_flags->>'snapshot_skipped',
                       o.http_status, o.parse_status, count(*), count(o.raw_snapshot),
                       coalesce(sum(octet_length(o.raw_snapshot)), 0)
                from listing_observation o join customer_listing l on l.id = o.listing_id
                where o.fetched_at >= cast(:since as timestamptz)
                group by 1, 2, 3, 4, 5 order by 1, 2, 3, 4, 5
                """,
                since=SINCE_R3,
            ),
        )
        # Policy invariants on live rows since 15:00.
        show(
            "INV1 failed fetch/parse rows WITHOUT snapshot since 15:00 (expect 0): count",
            q(
                c,
                """
                select count(*) from listing_observation o
                where o.fetched_at >= cast(:since as timestamptz)
                  and o.parse_status <> 'skipped'
                  and (coalesce(o.http_status, 0) <> 200 or o.parse_status <> 'ok')
                  and o.raw_snapshot is null
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "INV2 rows without snapshot lacking snapshot_skipped (excl. back-off 'skipped') since 15:00 (expect 0)",
            q(
                c,
                """
                select count(*) from listing_observation o
                where o.fetched_at >= cast(:since as timestamptz) and o.raw_snapshot is null
                  and o.parse_status <> 'skipped'
                  and coalesce(o.parse_flags->>'snapshot_skipped', '') <> 'unchanged'
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "INV3 skipped rows whose referent is NOT the latest earlier 200/ok row of the listing, "
            "or differs in price/availability/promo/parser_version (expect 0, 0): bad_referent, field_mismatch, total_skipped",
            q(
                c,
                """
                with s as (
                  select o.id, o.listing_id, o.fetched_at, o.extracted_price, o.extracted_availability,
                         o.extracted_promo_badge, o.parser_version,
                         (o.parse_flags->>'unchanged_since_observation_id')::bigint as ref
                  from listing_observation o
                  where o.fetched_at >= cast(:since as timestamptz)
                    and o.parse_flags->>'snapshot_skipped' = 'unchanged'
                ), latest as (
                  select s.id, (
                    select p.id from listing_observation p
                    where p.listing_id = s.listing_id and p.http_status = 200 and p.parse_status = 'ok'
                      and p.id < s.id
                    order by p.fetched_at desc, p.id desc limit 1
                  ) as expect_ref
                  from s
                )
                select
                  count(*) filter (where s.ref is distinct from latest.expect_ref),
                  count(*) filter (where p.extracted_price is distinct from s.extracted_price
                                   or p.extracted_availability is distinct from s.extracted_availability
                                   or p.extracted_promo_badge is distinct from s.extracted_promo_badge
                                   or p.parser_version is distinct from s.parser_version
                                   or p.listing_id <> s.listing_id),
                  count(*)
                from s join latest on latest.id = s.id
                left join listing_observation p on p.id = s.ref
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "INV4 skipped rows that also carry a status_transition (expect 0)",
            q(
                c,
                """
                select count(*) from listing_observation o
                where o.fetched_at >= cast(:since as timestamptz)
                  and o.parse_flags->>'snapshot_skipped' = 'unchanged'
                  and o.parse_flags ? 'status_transition'
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "INV5 'changed' rows whose fields equal the latest earlier 200/ok row (info: flag-only changes): count",
            q(
                c,
                """
                select count(*) from listing_observation o
                where o.fetched_at >= cast(:since as timestamptz)
                  and o.parse_flags->>'snapshot_stored' = 'changed'
                  and exists (
                    select 1 from (
                      select p.* from listing_observation p
                      where p.listing_id = o.listing_id and p.http_status = 200 and p.parse_status = 'ok' and p.id < o.id
                      order by p.fetched_at desc, p.id desc limit 1
                    ) p
                    where p.extracted_price is not distinct from o.extracted_price
                      and p.extracted_availability is not distinct from o.extracted_availability
                      and p.extracted_promo_badge is not distinct from o.extracted_promo_badge
                      and p.parser_version is not distinct from o.parser_version
                  )
                """,
                since=SINCE_R3,
            ),
        )
        show(
            "EDGE 200/ok rows carrying a fetch-side reason (count as 'previous successful' though stored as fetch_failed), all time / since 15:00",
            q(
                c,
                """
                select count(*), count(*) filter (where fetched_at >= cast(:since as timestamptz))
                from listing_observation
                where http_status = 200 and parse_status = 'ok' and parse_flags ? 'fetch_reason'
                """,
                since=SINCE_R3,
            ),
        )
        # Deletion / continuity.
        show(
            "TOTAL rows, min id, max id, (max-min+1) - count = id gaps, oldest fetched_at (SAST)",
            q(
                c,
                f"""
                select count(*), min(id), max(id), (max(id) - min(id) + 1) - count(*),
                       min(fetched_at) at time zone '{TZ}'
                from listing_observation
                """,
            ),
        )
        show(
            "gaps since id 3126: count, min, max, gaps",
            q(
                c,
                """
                select count(*), min(id), max(id), (max(id) - min(id) + 1) - count(*)
                from listing_observation where id > 3126
                """,
            ),
        )
        show(
            "earlier-recorded slots (VERIFY round 1 / IMPL round 3): slot, rows",
            q(
                c,
                f"""
                select {slot} as s, count(*)
                from listing_observation o
                where o.fetched_at >= cast('2026-10-07 17:00:00+02' as timestamptz)
                  and o.fetched_at < cast('2026-10-08 15:00:00+02' as timestamptz)
                group by 1 order by 1
                """,
            ),
        )
        show(
            "snapshots older than 90 d (expect 0); rows with snapshot_cleared (expect 0)",
            q(
                c,
                """
                select count(*) filter (where fetched_at < now() - interval '90 days' and raw_snapshot is not null),
                       count(*) filter (where parse_flags ? 'snapshot_cleared')
                from listing_observation
                """,
            ),
        )
        show(
            "sequence last_value (listing_observation id)",
            q(c, "select pg_sequence_last_value(pg_get_serial_sequence('listing_observation', 'id'))"),
        )
        show(
            "table sizes: total, heap, toast+index (pretty)",
            q(
                c,
                """
                select pg_size_pretty(pg_total_relation_size('listing_observation')),
                       pg_size_pretty(pg_relation_size('listing_observation')),
                       pg_size_pretty(pg_total_relation_size('listing_observation') - pg_relation_size('listing_observation'))
                """,
            ),
        )
        show(
            "indexes on listing_observation",
            q(c, "select indexname, indexdef from pg_indexes where tablename = 'listing_observation' order by 1"),
        )
        show(
            "RLS on listing_observation: relrowsecurity, relforcerowsecurity",
            q(c, "select relrowsecurity, relforcerowsecurity from pg_class where relname = 'listing_observation'"),
        )
        show(
            "EXPLAIN previous_successful_observation (listing 120)",
            q(
                c,
                """
                explain select id from listing_observation
                where listing_id = 120 and http_status = 200 and parse_status = 'ok'
                order by fetched_at desc, id desc limit 1
                """,
            ),
        )
        show(
            "EXPLAIN retention batch select",
            q(
                c,
                """
                explain select id, octet_length(raw_snapshot) from listing_observation
                where id > 0 and fetched_at < now() - interval '90 days' and raw_snapshot is not null
                order by id limit 5000
                """,
            ),
        )
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()
