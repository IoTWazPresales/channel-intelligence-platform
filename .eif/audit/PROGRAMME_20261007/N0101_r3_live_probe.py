"""N-0101 round 3: read-only measurement on cip (snapshot policy). No writes.

Usage (from apps/api, PYTHONPATH=., venv python):
  N0101_r3_live_probe.py baseline          -> max id, nullability, last runs' bytes
  N0101_r3_live_probe.py since <after_id>  -> observations with id > after_id

The URL comes from get_settings().database_url_sync in-process; nothing secret is printed.
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def _engine():
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url)


def _runs(c, where: str, params: dict) -> None:
    # Group observations into runs by the half-hour slot they were fetched in.
    rows = c.execute(
        text(
            f"""
            select date_trunc('hour', fetched_at) + interval '30 min' * floor(extract(minute from fetched_at) / 30) as slot,
                   min(id) as min_id, max(id) as max_id, count(*) as n,
                   count(raw_snapshot) as with_snapshot,
                   count(*) - count(raw_snapshot) as without_snapshot,
                   coalesce(sum(octet_length(raw_snapshot)), 0) as bytes,
                   min(fetched_at) as first_at, max(fetched_at) as last_at
            from listing_observation
            where {where}
            group by 1 order by 1
            """
        ),
        params,
    ).all()
    for r in rows:
        print(
            f"run slot {r.slot:%Y-%m-%d %H:%M} ids {r.min_id}..{r.max_id} n={r.n} "
            f"with_snapshot={r.with_snapshot} without={r.without_snapshot} bytes={r.bytes} "
            f"({r.bytes / 1e6:.2f} MB) {r.first_at:%H:%M:%S}-{r.last_at:%H:%M:%S}"
        )


def main() -> None:
    mode = sys.argv[1]
    eng = _engine()
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("transaction_read_only =", c.execute(text("show transaction_read_only")).scalar_one())
        if mode == "baseline":
            print(
                "raw_snapshot is_nullable =",
                c.execute(
                    text(
                        "select is_nullable from information_schema.columns "
                        "where table_name = 'listing_observation' and column_name = 'raw_snapshot'"
                    )
                ).scalar_one(),
            )
            print("max id =", c.execute(text("select max(id) from listing_observation")).scalar_one())
            print("rows =", c.execute(text("select count(*) from listing_observation")).scalar_one())
            print(
                "table size =",
                c.execute(text("select pg_size_pretty(pg_total_relation_size('listing_observation'))")).scalar_one(),
            )
            print("oldest fetched_at =", c.execute(text("select min(fetched_at) from listing_observation")).scalar_one())
            print(
                "with snapshot older than 90 d =",
                c.execute(
                    text(
                        "select count(*) from listing_observation where raw_snapshot is not null "
                        "and fetched_at < now() - interval '90 days'"
                    )
                ).scalar_one(),
            )
            _runs(c, "fetched_at > now() - interval '8 hours'", {})
        elif mode == "since":
            after = int(sys.argv[2])
            _runs(c, "id > :after", {"after": after})
            rows = c.execute(
                text(
                    """
                    select l.marketplace,
                           coalesce(o.parse_flags->>'snapshot_stored', 'skipped:' || coalesce(o.parse_flags->>'snapshot_skipped', 'none')) as why,
                           o.parse_status, count(*) as n,
                           count(o.raw_snapshot) as with_snapshot,
                           coalesce(sum(octet_length(o.raw_snapshot)), 0) as bytes
                    from listing_observation o join customer_listing l on l.id = o.listing_id
                    where o.id > :after
                    group by 1, 2, 3 order by 1, 2, 3
                    """
                ),
                {"after": after},
            ).all()
            for r in rows:
                print(
                    f"  {r.marketplace:9s} {r.why:26s} {r.parse_status:12s} n={r.n} "
                    f"with_snapshot={r.with_snapshot} bytes={r.bytes}"
                )
            t = c.execute(
                text(
                    "select count(*) as n from listing_observation where id > :after "
                    "and parse_flags ? 'status_transition'"
                ),
                {"after": after},
            ).scalar_one()
            print("  status transitions =", t)
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()
