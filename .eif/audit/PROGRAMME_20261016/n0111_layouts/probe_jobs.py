"""N-0111 layouts: READ-ONLY. Loaded CST jobs per source: file names, headers, mapping, fact rows."""
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
    cols = [r[0] for r in s.execute(text("select column_name from information_schema.columns where table_name='fact_customer_sellthrough' order by ordinal_position"))]
    print("fact cols:", cols)
    jobcol = next((c for c in cols if "job" in c), None)
    print("job col:", jobcol)
    rows = s.execute(text("""
      select j.id, sd.code, j.stage, j.status, j.file_name, j.created_at::date, j.file_headers is not null as hdr,
             j.field_mapping is not null as fm, j.staged_metadata->>'customer_id' as cust
      from import_job j join source_definition sd on sd.id=j.source_id join import_template t on t.id=sd.import_template_id
      where t.slug='customer_sell_through' and j.stage='loaded' order by sd.id, j.id""")).all()
    for r in rows:
        n = s.execute(text(f"select count(*) from fact_customer_sellthrough where {jobcol} = :j"), {"j": r.id}).scalar() if jobcol else None
        print(tuple(r), "fact rows:", n)
