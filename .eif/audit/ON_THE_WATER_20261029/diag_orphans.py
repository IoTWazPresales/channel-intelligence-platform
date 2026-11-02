"""READ-ONLY on cip: which facts lost their evidence line."""
from sqlalchemy import create_engine, text

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    print(con.execute(text("select current_database(), current_setting('transaction_read_only')")).one())
    print("facts with no evidence line, by (job, state, report_type): lines, units")
    for r in con.execute(text("select import_job_id, line_state, report_type, count(*), round(sum(quantity)) from fact_inbound_shipment where shipment_evidence_line_id is null group by 1,2,3 order by 4 desc limit 20")):
        print("  ", tuple(r))
    print("facts whose evidence line belongs to another job:", con.execute(text("select count(*) from fact_inbound_shipment f join shipment_evidence_line l on l.id=f.shipment_evidence_line_id where l.import_job_id is distinct from f.import_job_id")).scalar())
    print("fk on shipment_evidence_line_id:", con.execute(text("select pg_get_constraintdef(c.oid) from pg_constraint c where conrelid='fact_inbound_shipment'::regclass and contype='f' and pg_get_constraintdef(c.oid) like '%shipment_evidence_line_id%'")).all())
    con.rollback()
