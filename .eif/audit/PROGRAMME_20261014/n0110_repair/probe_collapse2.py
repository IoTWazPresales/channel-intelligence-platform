"""N-0110 repair: read-only. Which stored fact rows hold more than one source row, and why.

usage: python probe_collapse2.py <dbname>
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
        f = q("select id, source_key, site_label, customer_location_id, import_job_id, units_sold, reported_soh from fact_customer_sellthrough where id=160")
        print("fact 160", f)
        print(
            "fact 160 lines by job/site",
            q(
                "select import_job_id, count(*), count(distinct site_label), count(distinct resolved_location_id), "
                "count(distinct resolved_product_id) from import_customer_sellthrough_staging_line "
                "where fact_sellthrough_row_id=160 group by 1"
            ),
        )
        # Raw payload keys that look like a date column, across all applied lines.
        print(
            "payload keys (applied lines)",
            q(
                "select k, count(*) from import_customer_sellthrough_staging_line s, "
                "jsonb_object_keys(s.raw_row_payload) k where s.apply_status='applied' group by 1 order by 2 desc limit 60"
            ),
        )
        print(
            "jobs (applied)",
            q(
                "select s.import_job_id, j.created_at::date, count(*), count(distinct s.period_start_date), "
                "min(s.period_start_date), max(s.period_start_date), "
                "min(s.raw_row_payload->>'_cst_source_file'), count(distinct s.raw_row_payload->>'_cst_source_file') "
                "from import_customer_sellthrough_staging_line s join import_job j on j.id=s.import_job_id "
                "where s.apply_status='applied' group by 1,2 order by 1"
            ),
        )


if __name__ == "__main__":
    main()
