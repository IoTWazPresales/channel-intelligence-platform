"""READ-ONLY: field_mapping / file_headers / structure of loaded CST jobs."""
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
    for jid in (796, 1648, 1647, 1649, 1655, 1659, 1662, 1663):
        r = s.execute(text("select id, file_name, field_mapping, file_headers, staged_metadata->'report_structure_type', staged_metadata->'cst_batch_filenames', inferred_schema is not null from import_job where id=:i"), {"i": jid}).one()
        print("\nJOB", r[0], r[1])
        print("  field_mapping:", json.dumps(r[2])[:900])
        print("  file_headers:", json.dumps(r[3])[:900])
        print("  structure:", r[4], "| batch filenames:", r[5], "| inferred_schema:", r[6])
    print("\nrelevant staged_metadata keys of 1649:", sorted(s.execute(text("select staged_metadata from import_job where id=1649")).scalar().keys()))
