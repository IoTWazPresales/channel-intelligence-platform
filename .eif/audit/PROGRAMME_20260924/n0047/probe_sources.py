"""N-0047 read-only probe: replay each committed PM file through the real payload + date parse path
(no DB writes) and attribute every inverted cip dim_product window to its last writer and raw values.

Run from repo root: apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/n0047/probe_sources.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "apps/api")

import psycopg  # noqa: E402

from app.ingestion.infer import read_tabular  # noqa: E402
from app.services.catalog.product_import_sync import _parse_date_val  # noqa: E402
from app.services.imports.pm_dataframe_sanitize import strip_leading_descriptor_rows  # noqa: E402
from app.services.imports.product_master_workflow import (  # noqa: E402
    _row_payload_for_dim,
    decisions_to_field_mapping,
    display_name_column,
    technical_id_column,
)

c = psycopg.connect(host="localhost", port=5432, user="cip", password=__import__("os").environ["PGPASSWORD"], dbname="cip")
c.read_only = True
cur = c.cursor()
cur.execute("select current_database()")
print("current_database() =", cur.fetchone()[0], "(read-only session)")
cur.execute(
    "select j.id, j.file_name, j.mapping_decisions, r.storage_key from import_job j "
    "join raw_file_metadata r on r.job_id=j.id where j.template_slug='product_master' "
    "and j.stage='pm_committed' order by j.id"
)
jobs = cur.fetchall()
root = Path("apps/api/storage/uploads")
last: dict[str, tuple[int, object, object, object, object]] = {}  # sku -> (job, raw_ld, raw_eol, ld, eol)
for jid, fname, md, key in jobs:
    fm = decisions_to_field_mapping(md or {})
    ld_col = next((h for h, g in fm.items() if g == "launch_date"), None)
    eol_col = next((h for h, g in fm.items() if g == "end_of_life_date"), None)
    df = read_tabular(fname, (root / key).read_bytes())
    df, _ = strip_leading_descriptor_rows(df, tech_col=technical_id_column(fm), name_col=display_name_column(fm))
    types = Counter()
    n = 0
    for _, row in df.iterrows():
        pl = _row_payload_for_dim(row, fm)
        if not pl:
            continue
        n += 1
        raw_ld = row.get(ld_col) if ld_col else None
        raw_eol = row.get(eol_col) if eol_col else None
        types[(type(raw_ld).__name__, type(raw_eol).__name__)] += 1
        prev = last.get(pl["sku"])
        ld = _parse_date_val(pl["launch_date"]) if "launch_date" in pl else (prev[3] if prev else None)
        eol = _parse_date_val(pl["end_of_life_date"]) if "end_of_life_date" in pl else (prev[4] if prev else None)
        last[pl["sku"]] = (jid, raw_ld, raw_eol, ld, eol)
    print(f"job {jid} {fname}: payload rows={n} raw types (ld,eol)={dict(types.most_common(5))}")

cur.execute("select sku, launch_date, retired_date from dim_product where retired_date < launch_date")
inv = cur.fetchall()
by_job = Counter()
match = Counter()
raw_inverted = Counter()
examples: dict[str, list] = {}
for sku, ld, rd in inv:
    rec = last.get(sku)
    if rec is None:
        by_job["<no PM file row>"] += 1
        continue
    jid, raw_ld, raw_eol, pld, peol = rec
    by_job[jid] += 1
    same = (pld == ld and peol == rd)
    match["replay==db" if same else "replay!=db"] += 1
    if same and pld and peol and peol < pld:
        raw_inverted[jid] += 1
    examples.setdefault(f"job{jid}:{'same' if same else 'diff'}", []).append((sku, ld, rd, raw_ld, raw_eol))
print("inverted on cip:", len(inv))
print("last PM writer:", dict(by_job))
print("replay vs db:", dict(match))
print("inverted in source file itself (per last job):", dict(raw_inverted))
for k, rows in examples.items():
    print(k, rows[:4])

cur.execute("select sku, launch_date, retired_date from dim_product where launch_date='1970-01-01'")
epoch = cur.fetchall()
ep_by = Counter()
for sku, _, _ in epoch:
    rec = last.get(sku)
    ep_by[(rec[0], type(rec[1]).__name__, repr(rec[1])[:20]) if rec else "<none>"] += 1
print("1970-01-01 rows:", len(epoch), dict(ep_by.most_common(6)))
c.close()
