"""N-0065 round 4 discovery 4, READ ONLY, app role cip, scope '*': fact_inbound_shipment NULL-product rows
and their evidence-line identity lineage. Prints current_database() first."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "apps", "api")
os.chdir(API); sys.path.insert(0, API)
import sqlalchemy as sa
from sqlalchemy.pool import NullPool
from app.core.config import get_settings
url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})
with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    t0 = time.perf_counter()
    print("inbound null rows: total, with line link, line resolved, identity resolves:", c.execute(sa.text("""
      with ol as (select distinct o.evidence_line_id, o.line_identity_key from shipment_evidence_observation o where o.evidence_line_id is not null),
           res as (select distinct line_identity_key from shipment_evidence_observation where product_id is not null)
      select count(*), count(f.shipment_evidence_line_id), count(s.product_id),
             count(*) filter (where exists (select 1 from ol join res using (line_identity_key) where ol.evidence_line_id = f.shipment_evidence_line_id))
      from fact_inbound_shipment f left join shipment_evidence_line s on s.id = f.shipment_evidence_line_id
      where f.product_id is null""")).all(), round((time.perf_counter()-t0)*1000), "ms")
    print("inbound cols:", [r[0] for r in c.execute(sa.text("select column_name from information_schema.columns where table_name='fact_inbound_shipment' order by ordinal_position")).all()])
    print("inbound indexes:", [r[0] for r in c.execute(sa.text("select indexdef from pg_indexes where tablename='fact_inbound_shipment'")).all()])
    print("inbound owner/rls/force:", c.execute(sa.text("select pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity from pg_class where relname='fact_inbound_shipment'")).all())
    print("grants on obs/line/inbound/view:", c.execute(sa.text("""select table_name, grantee, string_agg(privilege_type, ',' order by privilege_type)
      from information_schema.role_table_grants where table_name in ('shipment_evidence_observation','shipment_evidence_line','fact_inbound_shipment','shipment_evidence_current')
      group by 1,2 order by 1,2""")).all())
    print("roles:", c.execute(sa.text("select rolname, rolsuper, rolbypassrls, rolcanlogin from pg_roles where rolname not like 'pg_%' order by 1")).all())
    c.rollback()
eng.dispose()
