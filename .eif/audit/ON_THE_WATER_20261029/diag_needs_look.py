"""READ-ONLY on cip: the facts the needs-a-look card selects, against the 27 Oct workbook's 12 Shipped-sheet lines with no ship confirm date."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, text

RAW = Path("C:/Users/warren_eliason/channel-intelligence-platform/apps/api/storage/uploads/imports/f8a61716696045269dce5769323418eb/ACZA Shipped Unshipped 20261027.xlsx")
TODAY = date(2026, 11, 2)
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


def d(v):
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else None)


wb = openpyxl.load_workbook(RAW, read_only=True, data_only=True)
it = wb["Shipped"].iter_rows(values_only=True)
hdr = [str(h).strip() if h is not None else "" for h in next(it)]
ix = {h: i for i, h in enumerate(hdr)}
raw = []
for r in it:
    if not any(v is not None for v in r):
        continue
    g = lambda n, r=r: r[ix[n]] if n in ix else None  # noqa: E731
    if d(g("Ship Confirm Date")) is None:
        raw.append({"delivery": norm(g("Delivery No")), "inv": norm(g("Invoice Line")), "order": norm(g("Order No.")), "line": norm(g("Order Line")), "item": norm(g("Item")),
                    "q": float(g("Qty") or 0), "exw": d(g("Exwork Date")), "pod": d(g("POD")), "billto": norm(g("Bill To")), "shipto": norm(g("Ship To"))})
wb.close()
p(f"workbook Shipped sheet, no ship confirm date: {len(raw)} lines, {sum(r['q'] for r in raw):,.0f} units")
for r in raw:
    p(f"   order {r['order']} line {r['line']} item {r['item']} qty {r['q']:g} exwork {r['exw']} POD {r['pod']} bill-to {r['billto'][:30]} | ship-to {r['shipto'][:30]}")

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    cutoff = TODAY - timedelta(days=7)
    rows = con.execute(text("""
        select f.id, f.import_job_id, f.report_type, f.source_sheet, f.line_state, f.source_key, f.fact_upsert_key, f.order_no, f.order_line, f.item_code, f.quantity,
               f.exwork_date, f.ship_confirm_date, f.pod_date, f.delivery_no, f.invoice_line, f.distributor_id, d.name, f.updated_at::date
        from fact_inbound_shipment f left join dim_distributor d on d.id = f.distributor_id
        where f.tenant_id = 'default' and f.line_state = 'open_order' and f.report_type = 'acza_workbook_shipped' and f.ship_confirm_date is null
          and f.pod_date is null and f.exwork_date is not null and f.exwork_date < :c order by f.id"""), {"c": cutoff}).all()
    p(f"\nthe card's rule on cip (open_order, report type shipped, no ship confirm, no POD, exwork before {cutoff}): {len(rows)} lines, {sum(float(r[10] or 0) for r in rows):,.0f} units")
    by_d = defaultdict(float)
    for r in rows:
        by_d[r[17]] += float(r[10] or 0)
    p("  by distributor:", {k: round(v) for k, v in by_d.items()})
    p("  by (job, sheet):", dict(Counter((r[1], r[3]) for r in rows)))
    wk = {(r["order"], r["line"], r["item"]): r for r in raw}
    for r in rows:
        k = (norm(r[7]), norm(r[8]), norm(r[9]))
        p(f"   fact {r[0]} job {r[1]} sheet {r[3]} state {r[4]} order {r[7]} line {r[8]} item {r[9]} qty {float(r[10] or 0):g} exwork {r[11]} key {r[6][:48] if r[6] else None} | in workbook list: {k in wk} | dist {r[17]} | updated {r[18]}")
    # the workbook's 12 against facts of any state
    p("\nthe workbook's 12 lines as facts on cip:")
    for k, r in wk.items():
        fs = con.execute(text("select id, import_job_id, line_state, report_type, source_sheet, quantity, exwork_date, ship_confirm_date, source_key from fact_inbound_shipment where tenant_id='default' and order_no = :o and item_code = :i"), {"o": k[0], "i": k[2]}).all()
        p(f"   order {k[0]} item {k[2]}: " + "; ".join(f"fact {f[0]} job {f[1]} {f[2]}/{f[3]}/{f[4]} qty {float(f[5] or 0):g} exw {f[6]} sc {f[7]}" for f in fs))
    con.rollback()
open("C:/Users/warren_eliason/channel-intelligence-platform/.eif/audit/ON_THE_WATER_20261029/diag_needs_look.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
