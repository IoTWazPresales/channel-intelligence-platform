"""READ-ONLY: columns of the tables the overnight investigations need, plus row counts. No writes."""
import json
import sys

from ro import q, run_ro

TABLES = sys.argv[1:] or ["fact_inbound_shipment", "shipment_evidence_line", "import_job"]


async def work(db):
    out = {}
    for t in TABLES:
        cols = await q(db, "select column_name, data_type from information_schema.columns where table_name = :t order by ordinal_position", t=t)
        out[t] = [f"{c['column_name']}:{c['data_type']}" for c in cols]
    print(json.dumps(out, indent=1))


run_ro(work)
