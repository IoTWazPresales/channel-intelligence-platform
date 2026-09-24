"""N-0047 read-only probe: PM job date-target mappings + raw file date columns (cip, read-only)."""
import sys
from pathlib import Path

import pandas as pd
import psycopg

c = psycopg.connect(host="localhost", port=5432, user="cip", password=__import__("os").environ["PGPASSWORD"], dbname="cip")
c.read_only = True
cur = c.cursor()
cur.execute("select current_database()")
print("current_database() =", cur.fetchone()[0])
cur.execute(
    "select j.id, j.mapping_decisions, r.storage_key from import_job j join raw_file_metadata r on r.job_id=j.id "
    "where j.template_slug='product_master' and j.stage='pm_committed' order by j.id"
)
root = Path("apps/api/storage/uploads")
for jid, md, key in cur.fetchall():
    t = {h: v.get("target") for h, v in md.items() if v.get("target")}
    dated = {h: v for h, v in t.items() if v in ("launch_date", "end_of_life_date", "lifecycle_status")}
    print(jid, key, "date/lifecycle targets:", dated)
    if "--files" in sys.argv:
        p = root / key
        if p.exists():
            df = pd.read_excel(p, nrows=5, dtype=str)
            cols = [h for h in df.columns if h in dated or any(s in h.lower() for s in ("date", "eol", "launch", "life"))]
            print("   cols:", cols)
            print(df[cols].head(5).to_string())
        else:
            print("   file missing", p)
c.close()
