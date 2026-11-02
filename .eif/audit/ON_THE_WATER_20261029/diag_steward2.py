"""READ-ONLY on cip: after the job 1697 re-process, is anything unresolved that the steward would have to decide?"""
from sqlalchemy import create_engine, text

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    print(con.execute(text("select current_database(), current_setting('transaction_read_only')")).one())
    q = """select {g} as grp, product_resolution_status p, distributor_resolution_status d, customer_resolution_status c,
                  (customer_dealer_token is not null and btrim(customer_dealer_token) <> '') has_token, count(*), round(sum(quantity))
           from shipment_evidence_line where import_job_id = 1697 group by 1,2,3,4,5 order by 1, 6 desc"""
    print("job 1697 evidence lines by (group, product, distributor, customer status, has customer token): lines, units")
    for r in con.execute(text(q.format(g="(source_key like '%|ord:%')"))):
        print("  ", tuple(r))
    print("the same for job 1696 (reference, untouched):")
    for r in con.execute(text(q.replace("1697", "1696").format(g="false"))):
        print("  ", tuple(r))
    print("candidates for job 1697 by entity and status:", [tuple(r) for r in con.execute(text("select entity_type, status, count(*) from import_entity_mapping_candidate where import_job_id=1697 group by 1,2"))])
    print("candidates by job (jobs with needs_review), top:", [tuple(r) for r in con.execute(text(
        "select import_job_id, entity_type, count(*) from import_entity_mapping_candidate where status='needs_review' group by 1,2 order by 3 desc limit 12"))])
    print("needs_review candidates touched today:", con.execute(text("select count(*) from import_entity_mapping_candidate where status='needs_review' and updated_at::date = current_date")).scalar())
    con.rollback()
