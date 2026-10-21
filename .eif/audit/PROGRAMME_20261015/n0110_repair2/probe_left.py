"""N-0110 repair 2, read-only: jobs owning the site-merged / repeated rows left. usage: python probe_left.py <db>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402
import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0])
    print(conn.execute("""
      select f.import_job_id, f.customer_id, count(*) from fact_customer_sellthrough f
      where (select count(*) from import_customer_sellthrough_staging_line s
             where s.fact_sellthrough_row_id=f.id and s.import_job_id=f.import_job_id and s.apply_status='applied') >= 2
        and (select sum(s.units_sold) from import_customer_sellthrough_staging_line s
             where s.fact_sellthrough_row_id=f.id and s.import_job_id=f.import_job_id and s.apply_status='applied') <> f.units_sold
      group by 1,2 order by 1""").fetchall())
