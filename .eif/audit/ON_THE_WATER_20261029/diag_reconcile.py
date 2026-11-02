"""READ-ONLY: reconcile the 27 Oct file's 169 at-sea lines / 14,278 units with cip's real at-sea set from job 1697.
SET TRANSACTION READ ONLY; nothing is written."""
from collections import defaultdict
from datetime import date

from sqlalchemy import create_engine, text

AS_OF = date(2026, 11, 1)
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
        select o.id, o.line_identity_key lik, o.order_no, o.item_code, o.customer_po, o.line_state, o.ship_confirm_date sc,
               o.on_board_date ob, o.port_eta_date eta, o.port_ata_date ata, o.pod_date pod, o.quantity q, o.ship_way way,
               o.report_type, o.source_sheet, o.evidence_line_id, o.invoice_line
        from shipment_evidence_observation o where o.import_job_id = 1697""")).mappings().all()
    p("rows in job 1697:", len(rows), "units", round(sum(float(r["q"] or 0) for r in rows)))
    sea = lambda r: "SEA" in (r["way"] or "").upper()  # noqa: E731
    q = lambda r: float(r["q"] or 0)  # noqa: E731

    def tot(rs):
        return f"{len(rs):>4} lines {sum(q(r) for r in rs):>8,.0f} units"

    # The user's definition: ship-confirmed, on board on or before 27 Oct, no ATA, sea.
    A = [r for r in rows if r["sc"] and r["ob"] and r["ob"] <= REPORT and not r["ata"] and sea(r)]
    p("\nA  ship-confirmed, on board <= 27 Oct, no ATA, sea:", tot(A), "(quoted: 169 lines 14,278 units)")
    # cip's rule as built: shipped, on board <= as-of, no ATA, no POD, sea.
    C = [r for r in rows if r["line_state"] == "shipped" and r["ob"] and r["ob"] <= AS_OF and not r["ata"] and not r["pod"] and sea(r)]
    p("C  cip's rule (shipped, on board <= 1 Nov, no ATA, no POD, sea):", tot(C))
    ida, idc = {r["id"] for r in A}, {r["id"] for r in C}

    p("\n-- in A, not in C (reason per group, first match):")
    groups = defaultdict(list)
    for r in A:
        if r["id"] in idc:
            continue
        if r["line_state"] != "shipped":
            g = f"line_state is {r['line_state']}"
        elif r["pod"]:
            g = "POD is set (delivered) though no ATA"
        else:
            g = "other"
        groups[g].append(r)
    for g, rs in sorted(groups.items(), key=lambda kv: -sum(q(r) for r in kv[1])):
        p(f"  {g:<44} {tot(rs)}")
    p("  total A not C:", tot([r for g in groups.values() for r in g]))
    p("-- in C, not in A:")
    g2 = defaultdict(list)
    for r in C:
        if r["id"] in ida:
            continue
        g = "no ship_confirm_date" if not r["sc"] else ("on board after 27 Oct (28 Oct-1 Nov)" if r["ob"] > REPORT else "other")
        g2[g].append(r)
    for g, rs in g2.items():
        p(f"  {g:<44} {tot(rs)}")
    p("  total C not A:", tot([r for g in g2.values() for r in g]))
    p("  A and C:", tot([r for r in A if r["id"] in idc]))
    p("  check: A = (A and C) + (A not C):", len(A), "=", len([r for r in A if r["id"] in idc]), "+", sum(len(g) for g in groups.values()))

    # POD detail for the A-not-C POD group
    pod_g = groups.get("POD is set (delivered) though no ATA", [])
    if pod_g:
        p("\n-- POD-set group: by ship_way / state / has-ETA / OB month:")
        d = defaultdict(lambda: [0, 0.0])
        for r in pod_g:
            k = (r["way"], str(r["ob"])[:7], "ETA" if r["eta"] else "no ETA")
            d[k][0] += 1
            d[k][1] += q(r)
        for k, v in sorted(d.items(), key=lambda kv: -kv[1][1])[:15]:
            p(f"   {k}: {v[0]} lines {v[1]:,.0f} units")
        pods = sorted({r["pod"] for r in pod_g})
        p("   POD dates span:", pods[0], "..", pods[-1])

    # how cip's facts see the A set: join by evidence_line_id -> fact
    p("\n-- A rows as facts on cip (fact via evidence line):")
    ev = [r["evidence_line_id"] for r in A if r["evidence_line_id"]]
    fm = {}
    for fr in con.execute(text("select id, shipment_evidence_line_id e, line_state, port_ata_date ata, pod_date pod from fact_inbound_shipment where shipment_evidence_line_id = any(:e)"), {"e": ev}).mappings():
        fm[fr["e"]] = fr
    cnt = defaultdict(lambda: [0, 0.0])
    for r in A:
        f = fm.get(r["evidence_line_id"])
        k = "no fact" if not f else f"fact {f['line_state']}" + (" +POD" if f["pod"] else "") + (" +ATA" if f["ata"] else "")
        cnt[k][0] += 1
        cnt[k][1] += q(r)
    for k, v in cnt.items():
        p(f"   {k:<28} {v[0]:>4} lines {v[1]:>8,.0f} units")

    # evidence line vs observation duplicates (multi-invoice rows collapse into one line)
    dup = con.execute(text("select count(*), count(distinct evidence_line_id) from shipment_evidence_observation where import_job_id=1697")).one()
    p("\nobservations vs distinct evidence lines in job 1697:", tuple(dup))
    con.rollback()

open(".eif/audit/ON_THE_WATER_20261029/diag_reconcile.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
