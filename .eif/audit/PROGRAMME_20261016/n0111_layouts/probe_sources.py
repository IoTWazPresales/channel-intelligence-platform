"""N-0111 layouts: READ-ONLY. Sell-through sources, their jobs and customers, and reporting customers.
usage (via dbrun.py): python probe_sources.py <dbname>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402

with SessionLocal() as s:
    db = s.execute(text("select current_database()")).scalar()
    print("current_database()", db, "(read-only)")
    if len(sys.argv) < 2 or sys.argv[1] != db:
        raise SystemExit("pass the database name")
    s.execute(text("SET TRANSACTION READ ONLY"))

    print("\n== templates")
    for r in s.execute(text("select id, slug, enabled, hidden, admin_only from import_template where slug in ('customer_sell_through','distributor_inventory')")):
        print(tuple(r))

    print("\n== CST sources: id, code, name, active, expected_template(customer_id), memory keys, jobs by status")
    rows = s.execute(text("""
        select sd.id, sd.code, sd.name, sd.is_active, sd.source_kind, sd.expected_template, sd.column_mapping_memory
        from source_definition sd join import_template t on t.id = sd.import_template_id
        where t.slug = 'customer_sell_through' order by sd.id""")).all()
    for r in rows:
        mem = r.column_mapping_memory if isinstance(r.column_mapping_memory, dict) else {}
        jobs = s.execute(text("""select status, stage, count(*) from import_job where source_id=:i group by 1,2 order by 3 desc"""), {"i": r.id}).all()
        print(r.id, repr(r.code), repr(r.name), r.is_active, r.source_kind, json.dumps(r.expected_template)[:200], "| mem keys:", sorted(mem.keys()), "| jobs:", [tuple(j) for j in jobs])

    print("\n== reporting customers (reports_expected) with key-account flag")
    for r in s.execute(text("""select c.id, c.name, c.is_key_account, rc.reports_expected, rc.expected_cadence
        from customer_report_config rc join dim_customer c on c.id = rc.customer_id order by rc.reports_expected desc, c.name""")):
        print(tuple(r))
