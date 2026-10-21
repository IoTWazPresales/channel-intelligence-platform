"""N-0110 repair: read-only. Stored sell-through rows that hold two or more source rows of the
load that last wrote them, split by what collapsed (sale day, site, or neither).

usage: python probe_overwrite.py <dbname>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_collapse import url_for  # noqa: E402

import psycopg  # noqa: E402

SQL = r"""
with lines as (
    select f.id fact_id, f.customer_id, f.units_sold fact_units,
           s.site_label, s.raw_location_token, s.units_sold line_units,
           -- a sale day the source row states (none expected on cip; Last Sold / Last Recv are attributes)
           coalesce(s.raw_row_payload->>'Date', s.raw_row_payload->>'Sale Date', s.raw_row_payload->>'Transaction Date',
                    s.raw_row_payload->>'Sales Date', s.raw_row_payload->>'Day') sale_day
    from fact_customer_sellthrough f
    join import_customer_sellthrough_staging_line s
      on s.fact_sellthrough_row_id = f.id and s.import_job_id = f.import_job_id
)
select fact_id, customer_id, max(fact_units) fact_units, count(*) n_lines,
       count(distinct sale_day) days, count(distinct coalesce(site_label, raw_location_token)) sites,
       sum(line_units) line_units
from lines group by fact_id, customer_id having count(*) > 1
"""


def main() -> None:
    db = sys.argv[1]
    with psycopg.connect(url_for(db)) as conn:
        conn.read_only = True
        print("current_database()", conn.execute("select current_database()").fetchone()[0])
        total = conn.execute("select count(*) from fact_customer_sellthrough").fetchone()[0]
        rows = conn.execute(SQL).fetchall()
        by_day = [r for r in rows if r[4] >= 2]
        by_site = [r for r in rows if r[4] < 2 and r[5] >= 2]
        same = [r for r in rows if r[4] < 2 and r[5] < 2]
        lost = lambda rs: float(sum((r[6] or 0) - (r[2] or 0) for r in rs))  # noqa: E731
        out = {
            "fact_rows": total,
            "rows_holding_2plus_source_rows": len(rows),
            "two_plus_sale_days_in_one_row": len(by_day),
            "two_plus_sites_in_one_row": len(by_site),
            "same_day_same_site_repeats": len(same),
            "units_in_source_rows_minus_stored_by_site": lost(by_site),
            "units_in_source_rows_minus_stored_repeats": lost(same),
            "site_collapse_by_customer": {},
        }
        for r in by_site:
            c = out["site_collapse_by_customer"].setdefault(str(r[1]), [0, 0.0])
            c[0] += 1
            c[1] += float((r[6] or 0) - (r[2] or 0))
        print(json.dumps(out, indent=1))
        future = conn.execute(
            "select f.customer_id, count(*), sum(f.units_sold) from fact_customer_sellthrough f "
            "join import_job j on j.id = f.import_job_id where f.period_start_date > j.created_at::date "
            "group by 1 order by 1"
        ).fetchall()
        print("rows dated after the load that wrote them (customer, rows, units):", future)


if __name__ == "__main__":
    main()
