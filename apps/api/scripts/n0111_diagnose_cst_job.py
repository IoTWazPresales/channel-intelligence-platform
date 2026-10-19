"""N-0111: why were a sell-through job's rows 'Missing product code or units'? (read only)

usage (API venv python, from apps/api): python scripts/n0111_diagnose_cst_job.py [job_id]
With no job id it takes the newest customer sell-through job. Prints current_database() first and
writes nothing. Shows the mapping the job used, the columns the parser resolved from it, and for the
file's rows how many have units, each identifier, and both.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.imports.customer_sell_through import _build_parse_mapping  # noqa: E402
from app.services.imports.parsers import customer_sell_through_flat as flat  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

with SessionLocal() as s:
    print("current_database() =", s.execute(text("select current_database()")).scalar())
    jid = int(sys.argv[1]) if len(sys.argv) > 1 else s.execute(
        text("select max(id) from import_job where staged_metadata ? 'customer_id'")
    ).scalar()
    job = s.get(ImportJob, jid)
    print(f"job {jid}: {job.file_name!r}")
    print("job.field_mapping:", job.field_mapping)
    mapping, _ = _build_parse_mapping(s, job, dict(job.field_mapping or {}), None)
    raws = s.query(RawFileMetadata).filter(RawFileMetadata.job_id == jid).all()
    for raw in raws:
        data = get_storage_backend().read(raw.storage_key)
        fm = dict(mapping)
        expected = flat.normalize_cst_expected_columns(fm.pop(flat.EXPECTED_COLUMNS_META_KEY, {}) or {})
        alias_index = flat._build_alias_index(fm, expected)
        df, first = flat._select_sheet_with_header(data, raw.storage_key.split("/")[-1], alias_index)
        print("\nheader row found at file row", first, "| rows", len(df))
        print("columns:", list(df.columns))
        col_map = flat._resolve_source_columns(list(df.columns), fm, expected)
        print("resolved:", {k: v for k, v in col_map.items() if v})
        u = col_map.get("units_sold")
        units_ok = df[u].map(lambda v: flat._parse_decimal(v) is not None) if u else None
        print("units column:", u, "| rows with a number:", int(units_ok.sum()) if u else "no units column")
        ids_ok = None
        for canon in flat.PRODUCT_IDENTIFIER_FIELDS:
            c = col_map.get(canon)
            if not c:
                continue
            ok = df[c].map(lambda v: flat._identifier_text(v) is not None)
            print(f"{canon}: column {c!r} | rows filled: {int(ok.sum())}")
            ids_ok = ok if ids_ok is None else (ids_ok | ok)
        if ids_ok is not None and units_ok is not None:
            print("rows with units AND an identifier:", int((ids_ok & units_ok).sum()))
        print("sample first rows:\n", df.head(3).to_string()[:1500])
        r = flat.parse_flat_report(data, raw.storage_key.split("/")[-1], mapping, jid)
        print("\nparser: rows", len(r.rows), "skipped", r.skipped_rows, "error", r.error)
