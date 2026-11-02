"""READ-ONLY: the pieces of the 27 Oct file around the quoted 169 / 14,278, by (ATA, POD, way) and the raw ATA/POD values."""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import create_engine, text

REPORT = date(2026, 10, 27)
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    rows = con.execute(text("""
        select o.line_state st, o.ship_confirm_date sc, o.on_board_date ob, o.port_eta_date eta, o.port_ata_date ata, o.pod_date pod,
               o.quantity q, upper(coalesce(o.ship_way,'')) way, o.source_sheet sheet, o.raw_source_row raw
        from shipment_evidence_observation o where o.import_job_id = 1697 and o.source_sheet = 'Shipped'""")).mappings().all()
    p("Shipped-sheet rows:", len(rows), "units", round(sum(float(r["q"] or 0) for r in rows)))
    q = lambda r: float(r["q"] or 0)  # noqa: E731
    base = [r for r in rows if r["sc"] is not None and r["ob"] is not None and r["ob"] <= REPORT]
    p("ship-confirmed, on board <= 27 Oct:", len(base), round(sum(q(r) for r in base)))
    grid = defaultdict(lambda: [0, 0.0])
    for r in base:
        k = ("ATA" if r["ata"] else "no ATA", "POD" if r["pod"] else "no POD", "sea" if "SEA" in r["way"] else r["way"])
        grid[k][0] += 1
        grid[k][1] += q(r)
    for k, v in sorted(grid.items(), key=lambda kv: -kv[1][1]):
        p(f"   {k}: {v[0]:>5} lines {v[1]:>9,.0f} units")
    noata = [r for r in base if not r["ata"]]
    p("no ATA (any POD, any way):", len(noata), round(sum(q(r) for r in noata)))
    noata_nopod = [r for r in noata if not r["pod"]]
    p("no ATA, no POD, any way:", len(noata_nopod), round(sum(q(r) for r in noata_nopod)))
    keys = [k for k in rows[0]["raw"].keys()] if rows else []
    p("raw headers:", [k for k in keys if any(w in k.lower() for w in ("ata", "eta", "pod", "board", "confirm", "ship way", "shipway", "method"))])
    ata_key = next((k for k in keys if k.lower().startswith("ata")), None)
    if ata_key:
        c = Counter(str(r["raw"].get(ata_key))[:12] for r in noata)
        p("raw ATA values where parsed ATA is null (top):", c.most_common(8))
    con.rollback()
open(".eif/audit/ON_THE_WATER_20261029/diag_reconcile3.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
