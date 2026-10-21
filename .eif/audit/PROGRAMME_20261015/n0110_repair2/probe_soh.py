"""N-0110 repair 2, read-only: on-hand stored by jobs 955, 956, 967. usage: python probe_soh.py <db>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402
import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0])
    print(conn.execute("select import_job_id, count(*), count(reported_soh), sum(units_sold) from fact_customer_sellthrough "
                       "where import_job_id in (955,956,967) group by 1 order by 1").fetchall())
