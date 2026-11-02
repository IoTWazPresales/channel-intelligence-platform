"""READ-ONLY diagnosis of the overdue vessels on cip (SET TRANSACTION READ ONLY; nothing is written).

Run from the project root with the API venv:  python -X utf8 -W ignore .eif/audit/ON_THE_WATER_20261029/diag_overdue.py
"""
import sys
from collections import Counter, defaultdict
from datetime import date

sys.path[:0] = ["apps/api", "."]

from sqlalchemy import create_engine, text  # noqa: E402

from app.services.imports.shipment_report_date import report_date_from_file_name  # noqa: E402
from app.services.shipping.on_the_water import (  # noqa: E402
    WaterConfig, WaterLine, classify, is_sea, lane_for, vessel_key,
)

AS_OF = date(2026, 11, 1)
NEWEST_JOB = 1697
cfg = WaterConfig()
eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


def fmt(d):
    return d.isoformat() if d else "-"


with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/read_only:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))

    # ---- 1. job 1697 and the other inbound shipment jobs
    p("\n=== 1. import jobs that carry shipment reports (tenant default) ===")
    jobs = con.execute(text("""
        select j.id, j.file_name, j.status, j.stage, j.completed_at::date,
               (select count(*) from shipment_evidence_observation o where o.import_job_id=j.id) obs,
               (select count(*) from shipment_evidence_line l where l.import_job_id=j.id) ev,
               (select count(*) from fact_inbound_shipment f where f.import_job_id=j.id) facts
        from import_job j where j.tenant_id='default' and j.template_slug='inbound_shipments' order by j.id""")).all()
    rep_by_job = {}
    for r in jobs:
        rd = report_date_from_file_name(r[1])
        rep_by_job[r[0]] = rd
        p(f"job {r[0]:>5} | report {fmt(rd)} | {r[2]:>10}/{r[3]:<8} | done {fmt(r[4])} | obs {r[5]:>6} ev {r[6]:>6} facts-now {r[7]:>6} | {r[1]}")
    j = [r for r in jobs if r[0] == NEWEST_JOB]
    p("job 1697:", j[0][:5] if j else "NOT FOUND")
    applied = [r for r in jobs if r[2] == "completed" and rep_by_job.get(r[0])]
    newest_applied = max(applied, key=lambda r: (rep_by_job[r[0]], r[0]))
    p("newest applied report by file-name date:", newest_applied[0], fmt(rep_by_job[newest_applied[0]]), newest_applied[1])

    # ---- 2. cip's at-sea facts, same selection as the endpoint
    rows = con.execute(text("""
        select f.id, f.import_job_id, j.file_name, f.fact_upsert_key, f.source_key, f.line_state, f.report_type, f.source_sheet,
               f.operating_unit, f.invoice_line, f.order_no, f.order_line, f.item_code, f.customer_po, f.quantity,
               f.on_board_date, f.port_eta_date, f.port_ata_date, f.pod_date, f.ship_way, f.origin_hub, f.deliver_port,
               f.vessel_name, f.voyage_no, f.shipment_evidence_line_id, f.updated_at::date, f.forwarder_code, f.delivery_no
        from fact_inbound_shipment f left join import_job j on j.id=f.import_job_id
        where f.tenant_id='default' and f.line_state in ('shipped','open_order')
          and (f.on_board_date is not null or f.port_ata_date is not null) and f.pod_date is null""")).mappings().all()
    facts = []
    for r in rows:
        w = WaterLine(id=r["id"], quantity=float(r["quantity"] or 0), line_state=r["line_state"], ship_way=r["ship_way"],
                      on_board=r["on_board_date"], port_eta=r["port_eta_date"], port_ata=r["port_ata_date"], pod=r["pod_date"],
                      hub=r["origin_hub"], deliver_port=r["deliver_port"], vessel_name=r["vessel_name"], voyage_no=r["voyage_no"])
        if classify(w, AS_OF) == "at_sea" and is_sea(w):
            lane, _ = lane_for(w.hub, cfg)
            facts.append((vessel_key(w, lane), w, dict(r)))
    vessels = defaultdict(list)
    for k, w, r in facts:
        vessels[k].append((w, r))
    tot_units = sum(w.quantity for _, w, _ in facts)
    p(f"\ncip at-sea (sea only, as of {AS_OF}): {len(facts)} lines, {tot_units:,.0f} units, {len(vessels)} vessels (endpoint said 162 / 13,516 / 14)")

    # ---- the newest report's observations
    obs = con.execute(text("""
        select o.id, o.line_identity_key, o.source_key, o.order_no, o.order_line, o.item_code, o.customer_po, o.invoice_line,
               o.line_state, o.on_board_date, o.port_eta_date, o.port_ata_date, o.pod_date, o.quantity, o.ship_way, o.origin_hub,
               o.deliver_port, o.vessel_name, o.voyage_no, o.report_type, o.source_sheet, o.evidence_line_id
        from shipment_evidence_observation o where o.import_job_id=:j"""), {"j": NEWEST_JOB}).mappings().all()
    p(f"\nobservations in job {NEWEST_JOB}: {len(obs)}")
    by_trip = defaultdict(list)
    for o in obs:
        by_trip[(o["order_no"], o["item_code"], o["customer_po"])].append(o)
    fact_by_ev = {}
    ev_ids = [o["evidence_line_id"] for o in obs if o["evidence_line_id"]]
    if ev_ids:
        for fr in con.execute(text("select id, fact_upsert_key, line_state, import_job_id, shipment_evidence_line_id, invoice_line, port_ata_date, pod_date from fact_inbound_shipment where shipment_evidence_line_id = any(:ids)"), {"ids": ev_ids}).mappings():
            fact_by_ev.setdefault(fr["shipment_evidence_line_id"], []).append(dict(fr))

    # ---- 4. ground truth from the 27 Oct report itself, classified the same way
    p("\n=== 4. at sea according to job 1697's own rows (same rule) ===")
    g_lines = []
    for o in obs:
        w = WaterLine(id=o["id"], quantity=float(o["quantity"] or 0), line_state=o["line_state"], ship_way=o["ship_way"],
                      on_board=o["on_board_date"], port_eta=o["port_eta_date"], port_ata=o["port_ata_date"], pod=o["pod_date"],
                      hub=o["origin_hub"], deliver_port=o["deliver_port"], vessel_name=o["vessel_name"], voyage_no=o["voyage_no"])
        if classify(w, AS_OF) == "at_sea" and is_sea(w):
            lane, _ = lane_for(w.hub, cfg)
            g_lines.append((vessel_key(w, lane), w, o))
    gv = defaultdict(list)
    for k, w, o in g_lines:
        gv[k].append((w, o))
    p(f"job 1697 at sea: {len(g_lines)} lines, {sum(w.quantity for _, w, _ in g_lines):,.0f} units, {len(gv)} vessel groups")
    for k, ms in sorted(gv.items(), key=lambda kv: min(x[0].port_eta or date.max for x in kv[1])):
        etas = sorted({x[0].port_eta for x in ms if x[0].port_eta})
        p(f"  {k[:60]:<60} lines {len(ms):>3} units {sum(x[0].quantity for x in ms):>7,.0f} ETA {fmt(etas[0] if etas else None)}..{fmt(etas[-1] if etas else None)}")
    states = Counter((o["line_state"], bool(o["port_ata_date"]), bool(o["pod_date"])) for o in obs)
    p("job 1697 rows by (line_state, has ATA, has POD):", dict(states))
    all_units_state = defaultdict(float)
    for o in obs:
        all_units_state[o["line_state"]] += float(o["quantity"] or 0)
    p("units by line_state in job 1697:", {k: round(v) for k, v in all_units_state.items()})

    # ---- 2/3. overdue vessels, line by line, against the newest report
    p("\n=== 2/3. overdue vessels: every line, and what job 1697 says about the same order_no + item + PO ===")
    cause_lines = Counter()
    cause_units = Counter()
    cause_by_vessel = defaultdict(Counter)
    detail_rows = []
    overdue = {k: ms for k, ms in vessels.items() if any((w.port_eta and w.port_eta < AS_OF) for w, _ in ms)}
    p(f"overdue vessels (any line with ETA before {AS_OF}): {len(overdue)}; lines {sum(len(v) for v in overdue.values())}; units {sum(w.quantity for v in overdue.values() for w, _ in v):,.0f}")
    for k, ms in sorted(overdue.items(), key=lambda kv: min(x[0].port_eta or date.max for x in kv[1])):
        etas = sorted({w.port_eta for w, _ in ms if w.port_eta})
        p(f"\n-- vessel {k} | lines {len(ms)} units {sum(w.quantity for w, _ in ms):,.0f} | ETA {fmt(etas[0] if etas else None)}..{fmt(etas[-1] if etas else None)}")
        for w, r in sorted(ms, key=lambda x: x[1]["id"]):
            trip = (r["order_no"], r["item_code"], r["customer_po"])
            matches = by_trip.get(trip, [])
            files = (r["file_name"] or "?")
            head = (f"fact {r['id']} job {r['import_job_id']} [{files}] key={r['fact_upsert_key']} state={r['line_state']} inv={r['invoice_line']} "
                    f"OB={fmt(w.on_board)} ETA={fmt(w.port_eta)} ATA={fmt(w.port_ata)} POD={fmt(w.pod)} qty={w.quantity:g} "
                    f"order={r['order_no']} item={r['item_code']} PO={r['customer_po']} sheet={r['source_sheet']} way={r['ship_way']}")
            if not matches:
                cause = "absent_from_1697"
                p("  " + head + "\n      -> job 1697: NO row with this order+item+PO")
            else:
                descs, same_fact, ata_or_pod, same_key = [], False, False, False
                for o in matches:
                    fs = fact_by_ev.get(o["evidence_line_id"], [])
                    fdesc = ";".join(f"fact {x['id']} key={x['fact_upsert_key']} st={x['line_state']}" for x in fs) or "no fact"
                    if any(x["id"] == r["id"] for x in fs):
                        same_fact = True
                    if o["port_ata_date"] or o["pod_date"]:
                        ata_or_pod = True
                    if any(x["fact_upsert_key"] == r["fact_upsert_key"] for x in fs):
                        same_key = True
                    descs.append(f"obs {o['id']} lik={o['line_identity_key']} inv={o['invoice_line']} st={o['line_state']} OB={fmt(o['on_board_date'])} ETA={fmt(o['port_eta_date'])} ATA={fmt(o['port_ata_date'])} POD={fmt(o['pod_date'])} qty={o['quantity']} | {fdesc}")
                if same_fact and not ata_or_pod:
                    cause = "same_fact_still_at_sea_in_1697"
                elif same_fact and ata_or_pod:
                    cause = "same_fact_but_1697_has_ATA_or_POD(fact_not_updated)"
                elif same_key:
                    cause = "same_key_other_fact"
                elif ata_or_pod:
                    cause = "identity_changed_1697_has_ATA_or_POD_under_other_key"
                else:
                    cause = "identity_changed_1697_still_at_sea_under_other_key"
                p("  " + head)
                for d in descs[:4]:
                    p("      -> job 1697: " + d)
                if len(descs) > 4:
                    p(f"      -> ... {len(descs) - 4} more rows with this order+item+PO")
            cause_lines[cause] += 1
            cause_units[cause] += w.quantity
            cause_by_vessel[k][cause] += 1
            detail_rows.append((k, r["id"], r["import_job_id"], r["file_name"], cause, w.quantity))

    p("\n=== cause summary over the overdue lines ===")
    for c, n in cause_lines.most_common():
        p(f"  {c:<62} lines {n:>4} units {cause_units[c]:>8,.0f}")
    p("by vessel:")
    for k, c in cause_by_vessel.items():
        p(f"  {k[:60]:<60} {dict(c)}")
    p("overdue lines by loading job/file:", dict(Counter((r[2], r[3]) for r in detail_rows)))

    # ---- compare whole at-sea list with job 1697
    p("\n=== cip at-sea facts (all, not only overdue) vs job 1697, by order+item+PO ===")
    cat = Counter()
    cat_units = Counter()
    for k, w, r in facts:
        trip = (r["order_no"], r["item_code"], r["customer_po"])
        ms = by_trip.get(trip)
        if not ms:
            c = "not_in_1697"
        elif any(classify(WaterLine(id=0, quantity=0, line_state=o["line_state"], on_board=o["on_board_date"], port_ata=o["port_ata_date"], pod=o["pod_date"]), AS_OF) == "at_sea" for o in ms):
            c = "in_1697_at_sea"
        elif any(o["port_ata_date"] or o["pod_date"] for o in ms):
            c = "in_1697_arrived_or_delivered"
        else:
            c = "in_1697_other_state:" + "/".join(sorted({o["line_state"] for o in ms}))
        cat[c] += 1
        cat_units[c] += w.quantity
    for c, n in cat.most_common():
        p(f"  {c:<50} lines {n:>4} units {cat_units[c]:>8,.0f}")
    gt = {(o["order_no"], o["item_code"], o["customer_po"]) for _, _, o in g_lines}
    cipt = {(r["order_no"], r["item_code"], r["customer_po"]) for _, _, r in facts}
    missing = gt - cipt
    p(f"at sea in 1697 but NOT at sea on cip: {len(missing)} order+item+PO keys")
    p(f"at sea in 1697 and at sea on cip: {len(gt & cipt)}")
    # what are the facts for those missing ones?
    if missing:
        miss = list(missing)[:8]
        for t in miss:
            fs = con.execute(text("select id, line_state, fact_upsert_key, import_job_id, port_ata_date, pod_date from fact_inbound_shipment where tenant_id='default' and order_no is not distinct from :o and item_code is not distinct from :i and customer_po is not distinct from :p"), {"o": t[0], "i": t[1], "p": t[2]}).all()
            p(f"   e.g. {t}: facts {[tuple(x) for x in fs][:4]}")
    con.rollback()

open(".eif/audit/ON_THE_WATER_20261029/diag_overdue.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
