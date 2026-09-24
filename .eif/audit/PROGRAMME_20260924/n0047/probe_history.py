"""N-0047 read-only probe: for each inverted cip window (all last-written by PM job 88), what did the
earlier committed PM file (job 31, same OEM feed, 2026-05-31) say for the same SKU? Also: serial re-derivation
of the 671 epoch (1970-01-01) rows, and inverted rows vs lifecycle/gap.
"""
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "apps/api")

import psycopg  # noqa: E402

from app.ingestion.infer import read_tabular  # noqa: E402
from app.services.imports.pm_dataframe_sanitize import strip_leading_descriptor_rows  # noqa: E402
from app.services.imports.product_master_workflow import (  # noqa: E402
    decisions_to_field_mapping,
    display_name_column,
    technical_id_column,
)
from app.services.catalog.product_import_sync import _parse_date_val  # noqa: E402

c = psycopg.connect(host="localhost", port=5432, user="cip", password=__import__("os").environ["PGPASSWORD"], dbname="cip")
c.read_only = True
cur = c.cursor()
cur.execute("select current_database()")
print("current_database() =", cur.fetchone()[0], "(read-only session)")
root = Path("apps/api/storage/uploads")


def file_dates(jid: int) -> dict[str, tuple]:
    cur.execute(
        "select j.file_name, j.mapping_decisions, r.storage_key from import_job j "
        "join raw_file_metadata r on r.job_id=j.id where j.id=%s",
        (jid,),
    )
    fname, md, key = cur.fetchone()
    fm = decisions_to_field_mapping(md)
    tc = technical_id_column(fm)
    ld_col = next(h for h, g in fm.items() if g == "launch_date")
    eol_col = next(h for h, g in fm.items() if g == "end_of_life_date")
    df = read_tabular(fname, (root / key).read_bytes())
    df, _ = strip_leading_descriptor_rows(df, tech_col=tc, name_col=display_name_column(fm))
    out = {}
    for _, row in df.iterrows():
        sku = str(row.get(tc) or "").strip()
        if sku:
            out[sku] = (row.get(ld_col), row.get(eol_col))
    return out


def as_date(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return date(1899, 12, 30) + timedelta(days=v)
    return _parse_date_val(v)


f31 = file_dates(31)
f88 = file_dates(88)
cur.execute("select sku, launch_date, retired_date, lifecycle_status from dim_product where retired_date < launch_date")
inv = cur.fetchall()
cls = Counter()
ex = {}
for sku, ld, rd, ls in inv:
    old = f31.get(sku)
    if old is None:
        k = "absent_in_job31"
    else:
        o_ld, o_rd = as_date(old[0]), as_date(old[1])
        if o_ld is None or o_rd is None:
            k = "job31_null_dates"
        elif (o_ld, o_rd) == (ld, rd):
            k = "job31_same_inverted"
        elif (o_ld, o_rd) == (rd, ld):
            k = "job31_exact_swap"
        elif o_ld <= o_rd:
            k = "job31_valid_other_window"
        else:
            k = "job31_other_inverted"
    cls[(k, ls)] += 1
    ex.setdefault(k, []).append((sku, ld, rd, old))
print("inverted:", len(inv))
for k, v in sorted(cls.items()):
    print("  ", k, v)
for k, rows in ex.items():
    print(k, rows[:3])

cur.execute("select sku, lifecycle_status from dim_product where launch_date='1970-01-01' and retired_date='1970-01-01'")
ep = Counter()
for sku, ls in cur.fetchall():
    raw = f88.get(sku)
    if raw is None or not isinstance(raw[0], int) or not isinstance(raw[1], int):
        ep["no_int_serial_in_job88"] += 1
        continue
    ld, rd = as_date(raw[0]), as_date(raw[1])
    ep["serial_inverted" if rd < ld else ("serial_equal" if rd == ld else "serial_valid")] += 1
print("epoch rows re-derived from job 88 serials:", dict(ep))
c.close()
