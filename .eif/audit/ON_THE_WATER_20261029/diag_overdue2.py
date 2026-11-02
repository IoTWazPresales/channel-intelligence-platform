"""READ-ONLY, part 2: the 39 overdue lines that are not still at sea in job 1697, looser matches and last-seen history;
and an attempt to reconcile job 1697's own units with the 15,009 quoted. SET TRANSACTION READ ONLY; nothing is written."""
import sys
from collections import Counter, defaultdict
from datetime import date

sys.path[:0] = ["apps/api", "."]

from sqlalchemy import create_engine, text  # noqa: E402

from app.services.imports.shipment_report_date import report_date_from_file_name  # noqa: E402

AS_OF = date(2026, 11, 1)
out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


def fmt(d):
    return d.isoformat() if d else "-"


eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/read_only:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    rep = {r[0]: report_date_from_file_name(r[1]) for r in con.execute(text("select id, file_name from import_job where tenant_id='default'"))}

    # --- the overdue facts that are not "same fact still at sea in 1697": at sea on cip, ETA before as-of, not backed by a 1697 at-sea row
    stale = con.execute(text("""
        select f.id, f.import_job_id, f.fact_upsert_key, f.source_key, f.line_state, f.order_no, f.item_code, f.customer_po,
               f.delivery_no, f.invoice_line, f.quantity, f.on_board_date, f.port_eta_date, f.port_ata_date, f.pod_date,
               f.ship_confirm_date, f.ship_way, f.shipment_evidence_line_id, f.report_type, f.source_sheet, f.operating_unit
        from fact_inbound_shipment f
        where f.tenant_id='default' and f.line_state in ('shipped','open_order')
          and (f.on_board_date is not null or f.port_ata_date is not null) and f.pod_date is null
          and f.port_ata_date is null and f.on_board_date <= :a and upper(coalesce(f.ship_way,'')) like '%SEA%'
          and f.line_state='shipped' and f.port_eta_date < :a
          and not exists (select 1 from shipment_evidence_observation o
                          where o.import_job_id=1697 and o.order_no is not distinct from f.order_no
                            and o.item_code is not distinct from f.item_code and o.customer_po is not distinct from f.customer_po)
        order by f.id"""), {"a": AS_OF}).mappings().all()
    p(f"\noverdue at-sea facts with no job-1697 row on order+item+PO: {len(stale)} lines, {sum(float(r['quantity'] or 0) for r in stale):,.0f} units")

    loose = Counter()
    rows_out = []
    for r in stale:
        o_item = con.execute(text("select count(*), min(line_state), max(line_state), count(*) filter (where port_ata_date is not null or pod_date is not null) "
                                  "from shipment_evidence_observation where import_job_id=1697 and order_no is not distinct from :o and item_code is not distinct from :i"),
                             {"o": r["order_no"], "i": r["item_code"]}).one()
        o_order = con.execute(text("select count(*) from shipment_evidence_observation where import_job_id=1697 and order_no is not distinct from :o"), {"o": r["order_no"]}).scalar()
        prefix = (r["fact_upsert_key"] or "").split("|")
        key_hit = 0
        if len(prefix) >= 2:
            key_hit = con.execute(text("select count(*) from fact_inbound_shipment where tenant_id='default' and import_job_id=1697 and fact_upsert_key like :k"), {"k": f"{prefix[0]}|{prefix[1]}%"}).scalar()
        deliv = con.execute(text("select count(*) from shipment_evidence_observation where import_job_id=1697 and delivery_no is not distinct from :d and item_code is not distinct from :i and :d is not null"), {"d": r["delivery_no"], "i": r["item_code"]}).scalar()
        # last time any report carried this line (by evidence-line identity) and what it said
        last = con.execute(text("""
            select o.import_job_id, o.line_state, o.port_eta_date, o.port_ata_date, o.pod_date, o.invoice_line, o.line_identity_key
            from shipment_evidence_observation o
            where o.line_identity_key = (select o2.line_identity_key from shipment_evidence_observation o2 where o2.evidence_line_id=:e limit 1)
            order by o.valid_from desc, o.id desc limit 1"""), {"e": r["shipment_evidence_line_id"]}).first()
        # observations anywhere (any report) with same order+item that show arrival/delivery
        later = con.execute(text("""select o.import_job_id, o.line_state, o.port_ata_date, o.pod_date from shipment_evidence_observation o
                                    where o.order_no is not distinct from :o and o.item_code is not distinct from :i
                                      and (o.port_ata_date is not null or o.pod_date is not null) order by o.valid_from desc limit 1"""),
                            {"o": r["order_no"], "i": r["item_code"]}).first()
        if o_item[0]:
            kind = "in_1697_on_order+item_not_PO" + ("_with_ATA/POD" if o_item[3] else "_still_at_sea/other")
        elif o_order:
            kind = "in_1697_on_order_only"
        elif key_hit:
            kind = "in_1697_on_delivery_key_only"
        elif deliv:
            kind = "in_1697_on_delivery_no+item"
        else:
            kind = "not_in_1697_by_any_key"
        loose[kind] += 1
        rows_out.append((r, kind, o_item, o_order, key_hit, last, later))
    p("loose matching of those lines against job 1697:", dict(loose))

    by_job = Counter((r["import_job_id"], rep.get(r["import_job_id"])) for r in stale)
    p("last loaded by (job, report date):", {f"{k[0]} ({fmt(k[1])})": v for k, v in sorted(by_job.items())})
    lastseen = Counter()
    for r, kind, o_item, o_order, key_hit, last, later in rows_out:
        lastseen[(last[0], fmt(rep.get(last[0])), last[1], bool(last[3] or last[4])) if last else "no observation"] += 1
    p("last report that carried the line -> (job, report date, state, has ATA/POD):", dict(lastseen))
    later_hit = sum(1 for x in rows_out if x[6])
    p("lines whose order+item shows an ATA or POD in some report:", later_hit)
    p("ship_confirm_date null:", sum(1 for r in stale if r["ship_confirm_date"] is None), "of", len(stale), "| invoice_line set:", sum(1 for r in stale if r["invoice_line"]), "| customer_po set:", sum(1 for r in stale if r["customer_po"]))
    p("fact_upsert_key shapes (parts):", dict(Counter(len((r["fact_upsert_key"] or "").split("|")) for r in stale)))
    p("report_type/sheet:", dict(Counter((r["report_type"], r["source_sheet"]) for r in stale)))
    p("\nper line (stale): fact | job | key | order | item | PO | kind | 1697 order+item rows | last carried by job/state/ATA/POD | later ATA/POD anywhere")
    for r, kind, o_item, o_order, key_hit, last, later in rows_out:
        p(f"  {r['id']} | {r['import_job_id']} | {r['fact_upsert_key']} | {r['order_no']} | {r['item_code']} | {r['customer_po']} | {kind} | {o_item[0]} | "
          f"{(last[0], last[1], fmt(last[3]), fmt(last[4])) if last else None} | {(later[0], fmt(later[2]), fmt(later[3])) if later else None}")

    # --- the 2 lines whose order+item+PO is in 1697 with ATA/POD while cip still has them at sea
    p("\n=== facts at sea on cip whose order+item+PO is in 1697 with an ATA or POD (identity change) ===")
    chg = con.execute(text("""
        select f.id, f.import_job_id, f.fact_upsert_key, f.invoice_line, f.quantity, f.on_board_date, f.port_eta_date, f.order_no, f.item_code, f.customer_po,
               o.id obs, o.line_identity_key, o.invoice_line o_inv, o.port_ata_date, o.pod_date, o.line_state, o.evidence_line_id,
               (select string_agg(x.id::text||':'||x.fact_upsert_key||':'||x.line_state||':'||coalesce(x.import_job_id::text,'-'), ' ; ') from fact_inbound_shipment x where x.shipment_evidence_line_id=o.evidence_line_id) o_facts
        from fact_inbound_shipment f
        join shipment_evidence_observation o on o.import_job_id=1697 and o.order_no is not distinct from f.order_no
             and o.item_code is not distinct from f.item_code and o.customer_po is not distinct from f.customer_po
        where f.tenant_id='default' and f.line_state='shipped' and f.port_ata_date is null and f.pod_date is null
          and f.on_board_date <= :a and f.port_eta_date < :a and upper(coalesce(f.ship_way,'')) like '%SEA%'
          and (o.port_ata_date is not null or o.pod_date is not null)"""), {"a": AS_OF}).mappings().all()
    for r in chg:
        p("  " + " | ".join(f"{k}={fmt(v) if isinstance(v, date) else v}" for k, v in r.items()))

    # --- reconcile job 1697's units with 15,009
    p("\n=== job 1697 units by class (all rows; as of 1 Nov) ===")
    grid = con.execute(text("""
        select line_state, coalesce(upper(ship_way),'-') way,
               (port_ata_date is not null) ata, (pod_date is not null) pod,
               case when on_board_date is null then 'no OB' when on_board_date > :a then 'OB future' else 'OB past' end ob,
               count(*), round(sum(quantity)) from shipment_evidence_observation where import_job_id=1697
        group by 1,2,3,4,5 order by 7 desc nulls last"""), {"a": AS_OF}).all()
    for g in grid[:30]:
        p("  ", tuple(g))
    tot = lambda cond: sum(float(g[6] or 0) for g in grid if cond(g))  # noqa: E731
    p("units: shipped, no ATA/POD, OB past, any way:", tot(lambda g: g[0] == "shipped" and not g[2] and not g[3] and g[4] == "OB past"))
    p("units: shipped, no ATA/POD, OB past, SEA:", tot(lambda g: g[0] == "shipped" and not g[2] and not g[3] and g[4] == "OB past" and "SEA" in g[1]))
    p("units: shipped, ATA set, no POD (arrived, not delivered):", tot(lambda g: g[0] == "shipped" and g[2] and not g[3]))
    p("units: shipped, no POD, OB known (at sea + arrived):", tot(lambda g: g[0] == "shipped" and not g[3] and g[4] != "no OB"))
    p("units: open_order with OB date:", tot(lambda g: g[0] == "open_order" and g[4] != "no OB"))
    p("units: shipped, no POD, any (incl. no OB):", tot(lambda g: g[0] == "shipped" and not g[3]))
    # ETA distinct values of the 1697 at-sea rows, any way
    eta = con.execute(text("""select port_eta_date, count(*), round(sum(quantity)) from shipment_evidence_observation
                              where import_job_id=1697 and line_state='shipped' and port_ata_date is null and pod_date is null and on_board_date is not null
                              group by 1 order by 1"""), {}).all()
    p("1697 shipped, no ATA/POD, OB known: by ETA (any ship way):", [(fmt(e[0]), e[1], int(e[2] or 0)) for e in eta])
    con.rollback()

open(".eif/audit/ON_THE_WATER_20261029/diag_overdue2.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
