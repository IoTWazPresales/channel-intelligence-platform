"""N-0101 round 3 (continued): read-only. Size of an observation row without its snapshot payload, on cip.

Usage (from apps/api, PYTHONPATH=., venv python): N0101_r3b_rowsize.py <after_id>
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    after = int(sys.argv[1])
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        r = c.execute(
            text(
                """
                select count(*) as n,
                       round(avg(pg_column_size(o.*))) as avg_row_bytes,
                       round(avg(pg_column_size(o.parse_flags))) as avg_flags_bytes
                from listing_observation o
                where o.id > :after and o.raw_snapshot is null
                """
            ),
            {"after": after},
        ).one()
        print(f"rows without snapshot n={r.n} avg_row_bytes={r.avg_row_bytes} avg_parse_flags_bytes={r.avg_flags_bytes}")
        for name in ("listing_observation",):
            s = c.execute(
                text(
                    "select pg_total_relation_size(:t) as total, pg_relation_size(:t) as heap, "
                    "pg_total_relation_size(:t) - pg_relation_size(:t) - pg_indexes_size(:t) as toast"
                ),
                {"t": name},
            ).one()
            print(f"{name} total={s.total} heap={s.heap} toast_etc={s.toast}")
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()
