"""N-0110 repair 2, read-only: sample _cst_derived payloads. usage: python probe_derived.py <db>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402
import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    print("current_database()", q("select current_database()")[0][0])
    for r in q("select import_job_id, raw_row_payload->'_cst_derived' from import_customer_sellthrough_staging_line "
               "where raw_row_payload ? '_cst_derived' and apply_status='applied' order by id limit 3"):
        print(r)
