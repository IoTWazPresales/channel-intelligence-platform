"""N-0110 repair 2, read-only: payload keys of applied CST staging lines. usage: python probe_keys.py <db>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110_repair"))
from probe_collapse import url_for  # noqa: E402
import psycopg  # noqa: E402

with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    print("current_database()", q("select current_database()")[0][0])
    print(q("select k, count(*) from import_customer_sellthrough_staging_line s, jsonb_object_keys(s.raw_row_payload) k "
            "where s.apply_status='applied' and left(k,1)='_' group by 1 order by 2 desc"))
    print(q("select raw_row_payload from import_customer_sellthrough_staging_line where apply_status='applied' limit 2"))
