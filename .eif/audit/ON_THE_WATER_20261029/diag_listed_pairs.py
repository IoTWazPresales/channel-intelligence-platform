"""READ-ONLY on cip: the 10 quantity-differs pairs against job 1697's evidence lines (after the re-process)."""
from sqlalchemy import create_engine, text

IDS = [113211, 113224, 134343, 134344, 134345, 134346, 134347, 134348, 134349, 134350]
eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    print(con.execute(text("select current_database(), current_setting('transaction_read_only')")).one())
    rows = con.execute(text("""
        select o.id, o.line_state, o.import_job_id, o.delivery_no, o.item_code, o.operating_unit, o.quantity,
               t.id twin, t.fact_upsert_key, t.quantity twin_qty, t.import_job_id twin_job, t.line_state twin_state, t.purchase_order_id,
               (select count(*) from shipment_evidence_line l where l.import_job_id = 1697 and l.delivery_no = o.delivery_no and l.item_code = o.item_code
                   and l.purchase_order_id = t.purchase_order_id) ev_lines,
               (select coalesce(sum(l.quantity), 0) from shipment_evidence_line l where l.import_job_id = 1697 and l.delivery_no = o.delivery_no and l.item_code = o.item_code
                   and l.purchase_order_id = t.purchase_order_id and l.line_state = 'shipped') ev_qty
        from fact_inbound_shipment o
        join fact_inbound_shipment t on t.tenant_id = o.tenant_id and t.id <> o.id and t.line_state = 'shipped' and t.purchase_order_id is not null
             and t.delivery_no = o.delivery_no and t.item_code = o.item_code and t.operating_unit is not distinct from o.operating_unit
             and coalesce(t.import_job_id,0) > coalesce(o.import_job_id,0)
        where o.id = any(:ids) order by o.id"""), {"ids": IDS}).all()
    for r in rows:
        print(tuple(r))
    con.rollback()
