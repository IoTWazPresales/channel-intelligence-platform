"""READ-ONLY on the uploaded 27 Oct workbook (the file is opened read-only, nothing is written back):
count the Shipped sheet by the user's definition and compare it with what job 1697 loaded."""
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl

PATH = Path("apps/api/storage/uploads/imports/f8a61716696045269dce5769323418eb/ACZA Shipped Unshipped 20261027.xlsx")
REPORT = date(2026, 10, 27)
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


wb = openpyxl.load_workbook(PATH, read_only=True, data_only=True)
p("sheets:", wb.sheetnames)
ws = wb["Shipped"]
it = ws.iter_rows(values_only=True)
header = [str(h).strip() if h is not None else "" for h in next(it)]
idx = {h: i for i, h in enumerate(header)}
p("columns with dates/ship/qty:", [h for h in header if any(w in h.lower() for w in ("date", "ship", "qty", "quantity", "pod", "eta", "ata", "board"))])
qty_col = next((h for h in header if h.lower() in ("quantity", "qty", "ship qty", "shipped quantity", "shipped qty")), None) or next((h for h in header if "qty" in h.lower() or "quantity" in h.lower()), None)
p("quantity column:", qty_col)
rows = [r for r in it if any(v is not None for v in r)]
p("data rows on Shipped:", len(rows))


def g(r, name):
    return r[idx[name]] if name in idx else None


way_col = "Ship Way" if "Ship Way" in idx else ("shipway" if "shipway" in idx else None)
sc, ob, ata, pod = "Ship Confirm Date", "On-Board Date", "ATA Date(Actual Port Arrival)", "POD"
cnt = defaultdict(lambda: [0, 0.0])
sel = []
for r in rows:
    q = g(r, qty_col) or 0
    try:
        q = float(q)
    except (TypeError, ValueError):
        q = 0.0
    way = str(g(r, way_col) or "").upper()
    d_sc, d_ob, d_ata, d_pod = as_date(g(r, sc)), as_date(g(r, ob)), as_date(g(r, ata)), as_date(g(r, pod))
    key = ("sc" if d_sc else "no sc", "ob<=27Oct" if d_ob and d_ob <= REPORT else ("ob later" if d_ob else "no ob"), "ATA" if d_ata else "no ATA",
           "POD" if d_pod else "no POD", "sea" if "SEA" in way else way or "-")
    cnt[key][0] += 1
    cnt[key][1] += q
    if d_sc and d_ob and d_ob <= REPORT and not d_ata and "SEA" in way:
        sel.append((q, r))
p(f"\nuser's definition on the raw sheet (ship-confirmed, on board <= 27 Oct, no ATA, sea): {len(sel)} lines {sum(q for q, _ in sel):,.0f} units")
p("by (ship confirm, on board, ATA, POD, way) - no POD, on board <= 27 Oct:")
for k, v in sorted(cnt.items(), key=lambda kv: -kv[1][1]):
    if k[3] == "no POD":
        p(f"   {k}: {v[0]:>5} lines {v[1]:>9,.0f} units")
wb.close()
open(".eif/audit/ON_THE_WATER_20261029/diag_raw_file.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
