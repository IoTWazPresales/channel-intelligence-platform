"""READ-ONLY, part 3: do the stale at-sea facts have a newer sibling under a PO-inclusive key (identity change)?
SET TRANSACTION READ ONLY; nothing is written."""
from collections import Counter
from datetime import date

from sqlalchemy import create_engine, text

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

    stale = con.execute(text("""
        select f.* from fact_inbound_shipment f
        where f.tenant_id='default' and f.line_state='shipped' and f.port_ata_date is null and f.pod_date is null
          and f.on_board_date <= :a and f.port_eta_date < :a and upper(coalesce(f.ship_way,'')) like '%SEA%'
          and f.import_job_id <> 1697
          and not exists (select 1 from shipment_evidence_observation o where o.import_job_id=1697
                          and o.order_no is not distinct from f.order_no and o.item_code is not distinct from f.item_code
                          and o.customer_po is not distinct from f.customer_po and o.port_ata_date is null and o.pod_date is null)
        order by f.id"""), {"a": AS_OF}).mappings().all()
    p(f"overdue at-sea facts not carried at sea by job 1697 (loaded by an older job): {len(stale)} lines, {sum(float(r['quantity'] or 0) for r in stale):,.0f} units")
    p("their purchase_order_id null:", sum(1 for r in stale if r["purchase_order_id"] is None), "| customer_po null:", sum(1 for r in stale if r["customer_po"] is None))

    sib_kind = Counter()
    sib_units = Counter()
    detail = []
    for r in stale:
        key = r["fact_upsert_key"] or ""
        sibs = con.execute(text("""select id, import_job_id, fact_upsert_key, line_state, port_eta_date, port_ata_date, pod_date, quantity, purchase_order_id, customer_po
                                   from fact_inbound_shipment where tenant_id='default' and id <> :i and fact_upsert_key like :k
                                   and order_no is not distinct from :o and item_code is not distinct from :it order by id"""),
                           {"i": r["id"], "k": key + "|%", "o": r["order_no"], "it": r["item_code"]}).all()
        if not sibs:
            kind = "no_sibling_under_PO_key"
        else:
            s = sibs[0]
            if s[6]:
                st = "sibling_delivered(POD)"
            elif s[5]:
                st = "sibling_arrived(ATA, no POD)"
            elif s[3] == "shipped":
                st = "sibling_still_at_sea"
            else:
                st = "sibling_" + str(s[3])
            kind = st
        sib_kind[kind] += 1
        sib_units[kind] += float(r["quantity"] or 0)
        detail.append((r, sibs, kind))
    p("\nstale facts by what their PO-key sibling says:")
    for k, n in sib_kind.most_common():
        p(f"  {k:<36} lines {n:>3} units {sib_units[k]:>7,.0f}")
    p("\nsibling job of those:", dict(Counter(d[1][0][1] for d in detail if d[1])))
    p("quantity equal to sibling:", sum(1 for d in detail if d[1] and float(d[1][0][7] or 0) == float(d[0]["quantity"] or 0)), "of", sum(1 for d in detail if d[1]))
    p("\nfact | old job | old key | sibling id | sibling job | sibling key | sibling state | ETA | ATA | POD | sibling PO id")
    for r, sibs, kind in detail:
        s = sibs[0] if sibs else None
        p(f"  {r['id']} | {r['import_job_id']} | {r['fact_upsert_key']} | " + (f"{s[0]} | {s[1]} | {s[2]} | {s[3]} | {fmt(s[4])} | {fmt(s[5])} | {fmt(s[6])} | {s[8]}" if s else "none"))

    # how widespread: old-key (no PO id) shipped facts that have a sibling under the PO key, any state
    p("\n=== how widespread: shipped facts with no purchase_order_id that have a PO-key sibling (all, not only at sea) ===")
    wide = con.execute(text("""
        select o.line_state, case when o.pod_date is not null then 'delivered' when o.port_ata_date is not null then 'arrived' else 'no ATA/POD' end old_view,
               case when s.pod_date is not null then 'delivered' when s.port_ata_date is not null then 'arrived' else 'no ATA/POD' end sib_view,
               count(*), round(sum(o.quantity))
        from fact_inbound_shipment o
        join fact_inbound_shipment s on s.tenant_id=o.tenant_id and s.id<>o.id and s.fact_upsert_key like o.fact_upsert_key||'|%'
             and s.order_no is not distinct from o.order_no and s.item_code is not distinct from o.item_code
        where o.tenant_id='default' and o.line_state='shipped' and o.purchase_order_id is null and o.fact_upsert_key like 'ship:%'
        group by 1,2,3 order by 4 desc"""), {}).all()
    for w in wide:
        p("  ", tuple(w))
    tot = con.execute(text("""select count(*), round(sum(o.quantity)) from fact_inbound_shipment o
                              where o.tenant_id='default' and o.line_state='shipped' and o.purchase_order_id is null and o.fact_upsert_key like 'ship:%'""")).one()
    p("all shipped facts with ship: key and no purchase_order_id:", tuple(tot))
    con.rollback()

open(".eif/audit/ON_THE_WATER_20261029/diag_overdue3.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
