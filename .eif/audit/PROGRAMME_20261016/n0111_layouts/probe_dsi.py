"""READ-ONLY: distributor sales & inventory sources, their mapping memory and jobs."""
from __future__ import annotations
import json, sys
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
    rows = s.execute(text("""select sd.id, sd.code, sd.name, sd.is_active, sd.expected_template, sd.column_mapping_memory
        from source_definition sd join import_template t on t.id=sd.import_template_id where t.slug='distributor_inventory' order by sd.id""")).all()
    for r in rows:
        mem = r.column_mapping_memory if isinstance(r.column_mapping_memory, dict) else {}
        jobs = s.execute(text("select status, stage, count(*) from import_job where source_id=:i group by 1,2 order by 3 desc"), {"i": r.id}).all()
        print(r.id, repr(r.code), repr(r.name), r.is_active, json.dumps(r.expected_template)[:160], "| memory keys:", sorted(mem.keys()),
              "| by_header_norm:", len((mem.get("by_header_norm") or {})) if mem else 0, "| jobs:", [tuple(j) for j in jobs])
    print("\nPinnacle distributor 29 name:", s.execute(text("select name from dim_distributor where id=29")).scalar())
    print("distributors that have DSI sell-out rows:", s.execute(text("select d.name, count(*) from fact_sales_sellout f join dim_distributor d on d.id=f.distributor_id group by 1 order by 2 desc limit 8")).all())
