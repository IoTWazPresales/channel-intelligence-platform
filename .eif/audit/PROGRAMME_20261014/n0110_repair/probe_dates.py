"""N-0110 repair: read-only. Payload columns whose values look like dates, on applied lines.

usage: python probe_dates.py <dbname>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_collapse import url_for  # noqa: E402

import psycopg  # noqa: E402


def main() -> None:
    db = sys.argv[1]
    with psycopg.connect(url_for(db)) as conn:
        conn.read_only = True
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
        print("current_database()", q("select current_database()")[0][0])
        rows = q(
            r"""
            select e.key, count(*), count(distinct e.value), min(e.value), max(e.value),
                   count(distinct s.import_job_id)
            from import_customer_sellthrough_staging_line s, jsonb_each_text(s.raw_row_payload) e
            where s.apply_status = 'applied'
              and e.value ~ '^\d{4}-\d{2}-\d{2}|^\d{1,2}/\d{1,2}/\d{4}|^\d{8}$'
            group by 1 order by 2 desc
            """
        )
        for r in rows:
            print("  date-like", r)
        print("raw_period_ref on applied", q("select count(*), count(raw_period_ref) from import_customer_sellthrough_staging_line where apply_status='applied'"))


if __name__ == "__main__":
    main()
