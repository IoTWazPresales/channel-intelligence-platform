"""READ-ONLY: row by row, the 169 lines / 14,278 units of the raw 27 Oct sheet against what job 1697 loaded and what cip holds."""
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


def norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def key(get):
    return (norm(get("Delivery No")), norm(get("Invoice Line")), norm(get("Order No.")), norm(get("Order Line")), norm(get("Item")), norm(get("Qty")))


wb = openpyxl.load_workbook(PATH, read_only=True, data_only=True)
it = wb["Shipped"].iter_rows(values_only=True)
hdr = [str(h).strip() if h is not None else "" for h in next(it)]
ix = {h: i for i, h in enumerate(hdr)}
raw = []
for r in it:
    if not any(v is not None for v in r):
        continue
    get = lambda n, r=r: r[ix[n]] if n in ix else None  # noqa: E731
    way = str(get("Ship Way") or "").upper()
    raw.append({"key": key(get), "sc": d(get("Ship Confirm Date")), "ob": d(get("On-Board Date")), "ata": d(get("ATA Date(Actual Port Arrival)")),
                "pod": d(get("POD")), "q": float(get("Qty") or 0), "way": way, "order": norm(get("Order No.")), "item": norm(get("Item")),
                "delivery": norm(get("Delivery No")), "inv": norm(get("Invoice Line")), "po": norm(get("Customer PO"))})
wb.close()
p("raw Shipped rows:", len(raw), "units", round(sum(r["q"] for r in raw)))
target = [r for r in raw if r["sc"] and r["ob"] and r["ob"] <= REPORT and not r["ata"] and "SEA" in r["way"]]
p("the 169:", len(target), round(sum(r["q"] for r in target)))

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    obs = con.execute(text("""select o.id, o.line_identity_key lik, o.evidence_line_id ev, o.line_state st, o.port_ata_date ata, o.pod_date pod, o.on_board_date ob,
                                     o.ship_confirm_date sc, o.quantity q, upper(coalesce(o.ship_way,'')) way, o.raw_source_row r, o.source_sheet sheet
                              from shipment_evidence_observation o where o.import_job_id=1697 and o.source_sheet='Shipped'""")).mappings().all()
    p("observations on the Shipped sheet:", len(obs), "units", round(sum(float(o["q"] or 0) for o in obs)))
    by_key = defaultdict(list)
    for o in obs:
        g = lambda n, o=o: o["r"].get(n)  # noqa: E731
        by_key[key(g)].append(o)
    lines = con.execute(text("select count(*), round(sum(quantity)) from shipment_evidence_line where import_job_id=1697 and source_sheet='Shipped'")).one()
    p("evidence lines (Shipped) for job 1697:", tuple(lines))

    groups = defaultdict(lambda: [0, 0.0])
    detail = defaultdict(list)
    for r in target:
        ms = by_key.get(r["key"], [])
        if ms:
            o = ms[0]
            if o["st"] == "shipped" and not o["ata"] and not o["pod"] and "SEA" in o["way"] and o["ob"] and o["ob"] <= REPORT:
                g = "A. loaded the same: at sea, no ATA, no POD"
            elif o["ata"] and not o["pod"]:
                g = "B. loaded with an ATA (arrived, not delivered)"
            elif o["pod"]:
                g = "C. loaded with a POD"
            else:
                g = f"D. loaded, state {o['st']}"
        else:
            # not loaded under this row key: is there another observation for the same delivery + item + order?
            sib = [o for k, v in by_key.items() if k[0] == r["delivery"] and k[4] == r["item"] and k[2] == r["order"] for o in v]
            g = "E. not loaded as its own row; same delivery+item+order loaded as another row" if sib else "F. not loaded at all"
        groups[g][0] += 1
        groups[g][1] += r["q"]
        detail[g].append((r, ms))
    p("\nthe 169 lines against job 1697 (observations):")
    for g in sorted(groups):
        p(f"  {g:<84} {groups[g][0]:>4} lines {groups[g][1]:>8,.0f} units")
    p("  total:", sum(v[0] for v in groups.values()), "lines", round(sum(v[1] for v in groups.values())), "units")

    # for E and F: what happened (the loaded sibling's state / how many raw rows share the key)
    for g in sorted(groups):
        if g[0] not in "EF":
            continue
        p(f"\n-- {g}: first 12 (delivery | invoice | order | item | qty | raw ATA/POD) and loaded sibling")
        for r, _ in detail[g][:12]:
            sib = [o for k, v in by_key.items() if k[0] == r["delivery"] and k[4] == r["item"] and k[2] == r["order"] for o in v]
            p(f"   {r['delivery']} | inv {r['inv']} | {r['order']} | {r['item']} | {r['q']:g} | sc {r['sc']} ob {r['ob']} | loaded sibling: " +
              "; ".join(f"obs {o['id']} st={o['st']} ata={o['ata']} pod={o['pod']} q={o['q']} inv={o['r'].get('Invoice Line')}" for o in sib[:3]))

    # raw rows that no observation carries, by whether they are in the 169, and why a row key can be missing
    raw_keys = Counter(r["key"] for r in raw)
    obs_keys = Counter(by_key.keys())
    missing_rows = sum(max(0, c - len(by_key.get(k, []))) for k, c in raw_keys.items())
    p("\nraw Shipped rows without an observation (multiset difference):", missing_rows)
    miss = [(r) for r in raw if len(by_key.get(r["key"], [])) == 0]
    p("  of which no ATA/POD and on board <= 27 Oct, sea:", len([r for r in miss if r["sc"] and r["ob"] and r["ob"] <= REPORT and not r["ata"] and "SEA" in r["way"]]))
    p("  units of the missing rows:", round(sum(r["q"] for r in miss)), "lines", len(miss))
    p("  missing rows by (ATA?, POD?, way):", dict(Counter(("ATA" if r["ata"] else "noATA", "POD" if r["pod"] else "noPOD", r["way"]) for r in miss).most_common(8)))
    con.rollback()
open(".eif/audit/ON_THE_WATER_20261029/diag_rowmatch.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
