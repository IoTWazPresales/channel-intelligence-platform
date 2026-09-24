"""Read-only probe of cip lineup cases for the N-0040 proof (no writes)."""
import json
import psycopg

conn = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname="cip")
conn.read_only = True
cur = conn.cursor()
cur.execute("select current_database()")
print("current_database() =", cur.fetchone()[0])
cur.execute(
    """
    select c.id, c.file_name, c.business_unit, c.product_line, c.period_label, c.superseded_by_case_id,
           c.source_context, j.staged_metadata, j.file_name
    from commercial_lineup_case c left join import_job j on j.id = c.import_job_id
    order by c.id
    """
)
for row in cur.fetchall():
    cid, fn, bu, pl, per, sup, sc, meta, jfn = row
    meta = meta if isinstance(meta, dict) else {}
    print(cid, repr(fn), bu, pl, per, sup, "| sc:", (json.dumps(sc)[:150] if sc else None),
          "| meta keys:", sorted(meta.keys())[:30])
    for k in ("lineup_parse_options", "lineup_bu_resolution"):
        if k in meta:
            print("    ", k, json.dumps(meta[k])[:400])
conn.rollback()
conn.close()
