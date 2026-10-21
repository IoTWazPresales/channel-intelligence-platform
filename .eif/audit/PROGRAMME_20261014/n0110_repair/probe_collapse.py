"""N-0110 repair: read-only probe of the old Monday overwrite. usage: python probe_collapse.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

import psycopg  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def url_for(db: str) -> str:
    s = get_settings()
    raw = (s.database_url_sync_migrate or s.database_url_sync).replace("postgresql+psycopg://", "postgresql://")
    return urlunparse(urlparse(raw)._replace(path="/" + db))


def main() -> None:
    db = sys.argv[1]
    with psycopg.connect(url_for(db)) as conn:
        conn.read_only = True
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
        print("current_database()", q("select current_database()")[0][0])
        print("fact grain", q("select period_grain, period_type, count(*) from fact_customer_sellthrough group by 1,2 order by 1,2"))
        print("staging grain", q("select period_grain, period_type, count(*) from import_customer_sellthrough_staging_line group by 1,2 order by 1,2"))
        print("staging apply", q("select apply_status, resolution_status, count(*) from import_customer_sellthrough_staging_line group by 1,2 order by 1,2"))
        # A sample legacy staging line with several lines per fact row.
        rows = q(
            """
            select s.fact_sellthrough_row_id, count(*) n, count(distinct s.raw_period_ref) refs,
                   min(s.raw_period_ref), max(s.raw_period_ref)
            from import_customer_sellthrough_staging_line s
            join fact_customer_sellthrough f on f.id = s.fact_sellthrough_row_id and f.import_job_id = s.import_job_id
            where s.apply_status = 'applied'
            group by 1 having count(*) > 1 order by n desc limit 5
            """
        )
        print("multi-line facts sample", rows)
        print(
            "staging columns",
            [r[0] for r in q("select column_name from information_schema.columns where table_name='import_customer_sellthrough_staging_line' order by ordinal_position")],
        )
        if rows:
            fid = rows[0][0]
            for r in q(f"select id, period_start_date, raw_period_ref, units_sold, reported_soh, site_label, raw_row_payload from import_customer_sellthrough_staging_line where fact_sellthrough_row_id={fid} order by id limit 4"):
                print("  line", r)


if __name__ == "__main__":
    main()
