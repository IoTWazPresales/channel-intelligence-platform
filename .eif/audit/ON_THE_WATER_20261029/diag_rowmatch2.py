"""READ-ONLY: are the 104 raw Shipped rows without an observation all collapsed by the (delivery, invoice line, item) source key?"""
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, text

PATH = Path("apps/api/storage/uploads/imports/f8a61716696045269dce5769323418eb/ACZA Shipped Unshipped 20261027.xlsx")
REPORT = date(2026, 10, 27)
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


def d(v):
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else None)


def norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


wb = openpyxl.load_workbook(PATH, read_only=True, data_only=True)
it = wb["Shipped"].iter_rows(values_only=True)
hdr = [str(h).strip() if h is not None else "" for h in next(it)]
ix = {h: i for i, h in enumerate(hdr)}
raw = []
for r in it:
    if not any(v is not None for v in r):
        continue
    g = lambda n, r=r: r[ix[n]] if n in ix else None  # noqa: E731
    raw.append({"full": (norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Order No.")), norm(g("Order Line")), norm(g("Item")), norm(g("Qty"))),
                "sk": (norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Item"))), "q": float(g("Qty") or 0), "sc": d(g("Ship Confirm Date")),
                "ob": d(g("On-Board Date")), "ata": d(g("ATA Date(Actual Port Arrival)")), "pod": d(g("POD")), "way": str(g("Ship Way") or "").upper(),
                "inv_blank": norm(g("Invoice Line")) == "", "po": norm(g("Customer PO"))})
wb.close()

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    obs = con.execute(text("select o.quantity q, o.raw_source_row r from shipment_evidence_observation o where o.import_job_id=1697 and o.source_sheet='Shipped'")).mappings().all()
    have = defaultdict(list)
    full_have = Counter()
    for o in obs:
        g = lambda n, o=o: o["r"].get(n)  # noqa: E731
        have[(norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Item")))].append(float(o["q"] or 0))
        full_have[(norm(g("Delivery No")), norm(g("Invoice Line")), norm(g("Order No.")), norm(g("Order Line")), norm(g("Item")), norm(g("Qty")))] += 1
    left = Counter(full_have)
    missing = []
    for r in raw:
        if left[r["full"]] > 0:
            left[r["full"]] -= 1
        else:
            missing.append(r)
    p("raw Shipped rows:", len(raw), "| observations:", len(obs), "| raw rows with no observation:", len(missing), f"({sum(r['q'] for r in missing):,.0f} units)")
    kinds = Counter()
    units = Counter()
    for r in missing:
        k = ("source key (delivery|invoice|item) is carried by another loaded row" if r["sk"] in have else "no loaded row with this source key") + \
            (", invoice line blank" if r["inv_blank"] else ", invoice line set")
        kinds[k] += 1
        units[k] += r["q"]
    for k, n in kinds.most_common():
        p(f"  {k:<100} {n:>4} rows {units[k]:>8,.0f} units")
    # group sizes: how many raw rows share one source key where the loaded row count is 1
    sk_count = Counter(r["sk"] for r in raw)
    shared = {k: c for k, c in sk_count.items() if c > 1}
    p("source keys carried by more than one raw row:", len(shared), "| raw rows in them:", sum(shared.values()), "| loaded rows for them:", sum(len(have.get(k, [])) for k in shared))
    p("  of those, invoice line blank:", sum(1 for k in shared if k[1] == ""), "keys")
    p("  units in those raw rows:", round(sum(r["q"] for r in raw if r["sk"] in shared)), "| units loaded for them:", round(sum(sum(have.get(k, [])) for k in shared)))
    atsea = [r for r in raw if r["sc"] and r["ob"] and r["ob"] <= REPORT and not r["ata"] and "SEA" in r["way"]]
    lost = [r for r in atsea if r in missing]
    p("of the 169 at-sea raw lines:", len(atsea), "| collapsed away:", len(lost), f"({sum(r['q'] for r in lost):,.0f} units) | all with blank invoice line:", all(r['inv_blank'] for r in lost))
    # same-quantity duplicates inside one source key (exact repeats) vs different orders
    same_order = sum(1 for k in shared if len({(r['full'][2], r['full'][3]) for r in raw if r['sk'] == k}) == 1)
    p("source keys whose raw rows all share one order+line (true repeats):", same_order, "of", len(shared))
    con.rollback()
open(".eif/audit/ON_THE_WATER_20261029/diag_rowmatch2.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
