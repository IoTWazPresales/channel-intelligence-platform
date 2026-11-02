"""READ-ONLY: rows and units lost to the (delivery, invoice line, item) source-key collapse, per ACZA job on cip, and whether the
lost lines later appear invoiced in a newer job. Reads the stored workbooks (opened read-only) and cip (read-only transaction)."""
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, text

from app.services.imports.shipment_report_date import report_date_from_file_name  # noqa: E402

ROOT = Path("C:/Users/warren_eliason/channel-intelligence-platform/apps/api/storage/uploads")
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


def norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    jobs = con.execute(text("""
        select j.id, j.file_name, r.storage_key from import_job j join raw_file_metadata r on r.job_id=j.id
        where j.tenant_id='default' and j.template_slug='inbound_shipments' and j.status='completed' and j.stage='loaded'
          and j.file_name ilike 'ACZA%' order by j.id""")).all()
    job_ids = [j[0] for j in jobs]
    rep = {j[0]: report_date_from_file_name(j[1]) for j in jobs}
    # later-invoiced lookup: lineage -> list of (job, numbered?) over all observations of the Shipped sheet
    obs = con.execute(text("""select import_job_id, order_no, order_line, item_code, (coalesce(btrim(invoice_line),'') <> '') as numbered
                              from shipment_evidence_observation where source_sheet='Shipped' and import_job_id = any(:j)"""), {"j": job_ids}).all()
    seen = defaultdict(lambda: {"numbered": set(), "blank": set()})
    for jid, o, l, i, n in obs:
        seen[(norm(o), norm(l), norm(i))]["numbered" if n else "blank"].add(jid)
    loaded = {r[0]: (r[1], float(r[2] or 0)) for r in con.execute(text(
        "select import_job_id, count(*), sum(quantity) from shipment_evidence_observation where source_sheet='Shipped' and import_job_id = any(:j) group by 1"), {"j": job_ids})}
    con.rollback()

p("job | report | raw Shipped rows/units | loaded obs rows/units | lost rows/units | blank-invoice key groups that collapsed | later invoiced | blank later only | never again")
tot = Counter()
for jid, fname, key in jobs:
    path = ROOT / key
    if not path.exists():
        p(f"{jid:>5} | {rep[jid]} | file missing: {key}")
        continue
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if "Shipped" not in wb.sheetnames:
        p(f"{jid:>5} | {rep[jid]} | no Shipped sheet: {wb.sheetnames}")
        continue
    it = wb["Shipped"].iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    ix = {h: i for i, h in enumerate(hdr)}
    need = ("Delivery No", "Invoice Line", "Item", "Order No.", "Order Line", "Qty")
    if not all(n in ix for n in need):
        p(f"{jid:>5} | {rep[jid]} | headers differ: missing {[n for n in need if n not in ix]}")
        continue
    groups = defaultdict(list)
    n_rows, units = 0, 0.0
    for r in it:
        if not any(v is not None for v in r):
            continue
        g = lambda n, r=r: r[ix[n]]  # noqa: E731
        q = float(g("Qty") or 0)
        n_rows += 1
        units += q
        groups[(norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Item")))].append((norm(g("Order No.")), norm(g("Order Line")), norm(g("Item")), q))
    wb.close()
    lost_rows, lost_units, collapsed_groups = 0, 0.0, 0
    lost_lineages = []
    for k, rows in groups.items():
        if len(rows) > 1:
            collapsed_groups += 1
            # one row survives per key (the loader keeps one); the others are lost
            keep = rows[-1]
            for r in rows[:-1]:
                lost_rows += 1
                lost_units += r[3]
                lost_lineages.append(r[:3])
    ld = loaded.get(jid, (0, 0.0))
    healed = blank_later = never = 0
    for lin in lost_lineages:
        s = seen.get(lin, {"numbered": set(), "blank": set()})
        if any(j > jid and (rep.get(j) or date.min) >= (rep.get(jid) or date.min) for j in s["numbered"]):
            healed += 1
        elif any(j > jid for j in s["blank"]):
            blank_later += 1
        else:
            never += 1
    p(f"{jid:>5} | {rep[jid]} | {n_rows:>5} / {units:>9,.0f} | {ld[0]:>5} / {ld[1]:>9,.0f} | {lost_rows:>4} / {lost_units:>7,.0f} (obs diff {n_rows - ld[0]} / {units - ld[1]:,.0f}) | "
      f"{collapsed_groups:>3} | {healed:>4} | {blank_later:>4} | {never:>4}")
    tot["rows"] += lost_rows
    tot["units"] += lost_units
    tot["healed"] += healed
    tot["blank_later"] += blank_later
    tot["never"] += never
p("\nall jobs, rows lost (counting a line once per job it was lost in):", tot["rows"], f"units {tot['units']:,.0f}")
p("  later invoiced in a newer job:", tot["healed"], "| seen later but still blank:", tot["blank_later"], "| never seen again:", tot["never"])
open(".eif/audit/ON_THE_WATER_20261029/diag_loss_per_job.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
