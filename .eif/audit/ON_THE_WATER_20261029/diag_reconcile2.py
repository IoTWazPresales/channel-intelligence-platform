"""READ-ONLY: which definition of 'at sea' over job 1697 gives 169 lines / 14,278 units? Brute force over the conditions.
SET TRANSACTION READ ONLY; nothing is written."""
import itertools
from datetime import date

from sqlalchemy import create_engine, text

REPORT, AS_OF = date(2026, 10, 27), date(2026, 11, 1)
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
               o.quantity q, upper(coalesce(o.ship_way,'')) way, o.source_sheet sheet, o.report_type rt
        from shipment_evidence_observation o where o.import_job_id = 1697""")).mappings().all()
    p("observations:", len(rows))
    p("source_sheet/report_type:", sorted({(r["sheet"], r["rt"]) for r in rows}))
    q = lambda r: float(r["q"] or 0)  # noqa: E731
    sc_opts = {"sc required": lambda r: r["sc"] is not None, "sc any": lambda r: True, "sc <= 27 Oct": lambda r: r["sc"] is not None and r["sc"] <= REPORT}
    ob_opts = {"ob <= 27 Oct": lambda r: r["ob"] is not None and r["ob"] <= REPORT, "ob <= 1 Nov": lambda r: r["ob"] is not None and r["ob"] <= AS_OF,
               "ob any": lambda r: True, "ob null": lambda r: r["ob"] is None}
    ata_opts = {"no ATA": lambda r: r["ata"] is None, "ATA any": lambda r: True}
    pod_opts = {"no POD": lambda r: r["pod"] is None, "POD any": lambda r: True}
    st_opts = {"shipped": lambda r: r["st"] == "shipped", "state any": lambda r: True, "shipped+open": lambda r: r["st"] in ("shipped", "open_order")}
    way_opts = {"sea": lambda r: "SEA" in r["way"], "any way": lambda r: True, "not air": lambda r: "AIR" not in r["way"] and r["way"] != "EXPRESS"}
    hits = []
    for combo in itertools.product(sc_opts.items(), ob_opts.items(), ata_opts.items(), pod_opts.items(), st_opts.items(), way_opts.items()):
        fs = [c[1] for c in combo]
        sel = [r for r in rows if all(f(r) for f in fs)]
        n, u = len(sel), sum(q(r) for r in sel)
        hits.append((abs(n - 169) + abs(u - 14278) / 50, n, u, " | ".join(c[0] for c in combo)))
    hits.sort()
    p("\nclosest definitions to 169 lines / 14,278 units:")
    for h in hits[:12]:
        p(f"  {h[1]:>5} lines {h[2]:>9,.0f} units  {h[3]}")
    exact = [h for h in hits if h[1] == 169 or round(h[2]) == 14278]
    p("exact on lines or units:", exact[:10])
    con.rollback()

open(".eif/audit/ON_THE_WATER_20261029/diag_reconcile2.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
