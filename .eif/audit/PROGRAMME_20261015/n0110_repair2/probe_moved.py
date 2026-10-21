"""N-0110 repair 2, read-only: superseded rows per customer and reason. usage: python probe_moved.py <db>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402
import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0])
    for r in conn.execute("select customer_id, reason, count(*), sum(units_sold), sum(reported_soh) "
                          "from fact_customer_sellthrough_superseded group by 1,2 order by 1,2").fetchall():
        print("superseded", r)
    for r in conn.execute("select customer_id, count(*) from import_customer_sellthrough_staging_line s "
                          "join fact_customer_sellthrough f on f.id=s.fact_sellthrough_row_id "
                          "where s.apply_status='duplicate' group by 1").fetchall():
        print("duplicate lines", r)
