"""READ-ONLY: header sets of the loaded jobs of customers 15 (Makro), 57 (Game), 20 (Takealot): what differs between files."""
from __future__ import annotations
import os, sys
from pathlib import Path
API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
from sqlalchemy import select, text  # noqa: E402
from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.imports.cst_layouts import cst_template_expected_columns, sniff_columns, normalize_header  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

with SessionLocal() as s:
    db = s.execute(text("select current_database()")).scalar()
    print("current_database()", db, "(read-only)")
    if len(sys.argv) < 2 or sys.argv[1] != db:
        raise SystemExit("pass the database name")
    s.execute(text("SET TRANSACTION READ ONLY"))
    exp = cst_template_expected_columns(s)
    sets = {}
    for jid in (1659, 1660, 1661, 1665, 1662, 1663, 1664, 1667, 1648, 1649, 1650, 1651, 1652):
        j = s.get(ImportJob, jid)
        r = s.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == jid)).first()
        info = sniff_columns(os.path.basename(r.storage_key), get_storage_backend().read(r.storage_key), exp, dict(j.field_mapping or {}))
        sets[jid] = [normalize_header(c) for c in info["columns"]]
        print(jid, j.file_name, len(sets[jid]))
    base = {15: 1659, 57: 1662, 20: 1648}
    for cust, b in base.items():
        for jid, cols in sets.items():
            if jid == b: continue
            if (cust == 15 and jid in (1659,1660,1661,1665)) or (cust == 57 and jid in (1662,1663,1664,1667)) or (cust == 20 and jid in (1648,1649,1650,1651,1652)):
                add = [c for c in cols if c not in sets[b]]; gone = [c for c in sets[b] if c not in cols]
                print(f"\ncust {cust}: job {jid} vs {b}: +{add[:14]}  -{gone[:14]}")
