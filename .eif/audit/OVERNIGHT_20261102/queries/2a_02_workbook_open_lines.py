"""2a step 2 (reads only the workbook file; no database): the open-order lines of the 27 Oct workbook.

Open = every row of 'Unship', every row of 'BOM not ready', and every 'Shipped' row whose Ship Confirm Date is blank or
later than the report date (2026-10-27, the single YYYYMMDD in the file name). That is Warren's rule (28-29 Oct).
Output: 2a_workbook_open_lines.json; summary on stdout.
"""
import datetime as dt
import json
import pathlib
from collections import defaultdict

import openpyxl

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
XLSX = ROOT / "apps/api/storage/uploads/imports/f8a61716696045269dce5769323418eb/ACZA Shipped Unshipped 20261027.xlsx"
REPORT_DATE = dt.date(2026, 10, 27)


def norm(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return None


def sheet_rows(ws):
    it = ws.iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else "" for h in next(it)]
    idx = {}
    for i, h in enumerate(head):
        idx.setdefault(h, i)
    for n, row in enumerate(it, start=2):
        yield n, idx, row


def get(idx, row, *names):
    for nm in names:
        if nm in idx:
            return row[idx[nm]]
    return None


def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    out = []
    stats = defaultdict(lambda: [0, 0.0])
    for ws in wb.worksheets:
        for n, idx, row in sheet_rows(ws):
            if ws.title == "Unship":
                rec = dict(sheet="Unship", row=n, order_no=norm(get(idx, row, "Order No.")), order_line=norm(get(idx, row, "Order Line")),
                           delivery_no=norm(get(idx, row, "Delivery No")), item=norm(get(idx, row, "Item")), po=norm(get(idx, row, "Customer PO")),
                           bill_to=norm(get(idx, row, "Bill To")), qty=get(idx, row, "Qty"), ship_confirm=to_date(get(idx, row, "Ship Confirm Date")))
                if rec["qty"] is None and rec["order_no"] is None:
                    continue
            elif ws.title == "BOM not ready":
                rec = dict(sheet="BOM", row=n, order_no=norm(get(idx, row, "SO#")) or norm(get(idx, row, "RET/AUT/QUOTE")), order_line=None, delivery_no=None, item=norm(get(idx, row, "Item")),
                           po=norm(get(idx, row, "PO")), bill_to=norm(get(idx, row, "Bill To")), qty=get(idx, row, "QTY"), ship_confirm=None)
                if rec["qty"] is None and rec["item"] is None:
                    continue
            elif ws.title == "Shipped":
                sc = to_date(get(idx, row, "Ship Confirm Date"))
                if sc is not None and sc <= REPORT_DATE:
                    stats["Shipped (confirmed, not open)"][0] += 1
                    stats["Shipped (confirmed, not open)"][1] += float(get(idx, row, "Qty") or 0)
                    continue
                rec = dict(sheet="Shipped-open", row=n, order_no=norm(get(idx, row, "Order No.")), order_line=norm(get(idx, row, "Order Line")),
                           delivery_no=norm(get(idx, row, "Delivery No")), item=norm(get(idx, row, "Item")), po=norm(get(idx, row, "Customer PO")),
                           bill_to=norm(get(idx, row, "Bill To")), qty=get(idx, row, "Qty"), ship_confirm=sc)
                rec["why_open"] = "no ship confirm date" if sc is None else "ship confirm date after report date"
            else:
                continue
            rec["qty"] = float(rec["qty"] or 0)
            if rec["ship_confirm"]:
                rec["ship_confirm"] = rec["ship_confirm"].isoformat()
            out.append(rec)
            stats[rec["sheet"]][0] += 1
            stats[rec["sheet"]][1] += rec["qty"]
    (HERE / "2a_workbook_open_lines.json").write_text(json.dumps(out), encoding="utf-8")
    tot_lines = sum(v[0] for k, v in stats.items() if not k.startswith("Shipped (conf"))
    tot_units = sum(v[1] for k, v in stats.items() if not k.startswith("Shipped (conf"))
    for k, v in stats.items():
        print(k, v)
    print("open total lines", tot_lines, "units", tot_units)


main()
