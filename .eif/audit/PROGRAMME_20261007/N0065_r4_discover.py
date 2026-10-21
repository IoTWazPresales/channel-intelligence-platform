"""N-0065 round 4 discovery, READ ONLY, app role cip. Usage: python <this> cip|cip_test

Prints current_database() first. Every connection is default_transaction_read_only=on with a
60 s statement timeout. Scope '*' is bound so the app role reads every row.
"""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

target = sys.argv[1]
assert target in ("cip", "cip_test")
url = get_settings().database_url_sync
base, _, tail = url.rpartition("/")
query = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
url = f"{base}/{target}{query}".replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})


def q(c, sql, **kw):
    return c.execute(sa.text(sql), kw).all()


with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == target
    print("role:", q(c, "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user"))
    print("alembic:", q(c, "select version_num from alembic_version"))
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    for t in ("shipment_evidence_observation", "shipment_evidence_line"):
        cols = [r[0] for r in q(c, "select column_name from information_schema.columns where table_name=:t order by ordinal_position", t=t)]
        print(f"{t} columns:", cols)
        print(f"  owner/rls/force:", q(c, """select pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity
                                            from pg_class where relname=:t""", t=t))
        print("  policies:", q(c, "select policyname, cmd from pg_policies where tablename=:t order by 1", t=t))
        print("  indexes:", [r[0] for r in q(c, "select indexdef from pg_indexes where tablename=:t", t=t)])
    print("all policies not cip_pl_*:", q(c, "select tablename, policyname from pg_policies where policyname not like 'cip_pl_%' order by 1"))
    print("tables with line_identity_key:", [r[0] for r in q(c, """select c.table_name from information_schema.columns c
        join information_schema.tables t on t.table_name=c.table_name and t.table_schema=c.table_schema
        where c.table_schema='public' and c.column_name='line_identity_key' and t.table_type='BASE TABLE'""")])
    print("views/matviews in public:", q(c, "select relname, relkind from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and relkind in ('v','m')"))
    print("functions cip_%:", q(c, "select proname, prosecdef, pg_get_userbyid(proowner), proconfig from pg_proc where proname like 'cip_%' order by 1"))

    # Observation / line product facts
    print("obs total / null product / unsuperseded:", q(c, """select count(*), count(*) filter (where product_id is null),
        count(*) filter (where superseded_by_id is null) from shipment_evidence_observation"""))
    print("line total / null product:", q(c, "select count(*), count(*) filter (where product_id is null) from shipment_evidence_line"))
    print("obs null o.product_id but sel.product_id not null:", q(c, """select count(*) from shipment_evidence_observation o
        join shipment_evidence_line s on s.id=o.evidence_line_id where o.product_id is null and s.product_id is not null"""))
    print("obs o.product_id <> sel.product_id (both set):", q(c, """select count(*) from shipment_evidence_observation o
        join shipment_evidence_line s on s.id=o.evidence_line_id where o.product_id <> s.product_id"""))
    print("  ... of which different product_line:", q(c, """select count(*) from shipment_evidence_observation o
        join shipment_evidence_line s on s.id=o.evidence_line_id join dim_product a on a.id=o.product_id
        join dim_product b on b.id=s.product_id where a.product_line is distinct from b.product_line"""))
    print("identities with >1 distinct resolved product (o.product_id):", q(c, """select count(*) from (
        select line_identity_key from shipment_evidence_observation where product_id is not null
        group by 1 having count(distinct product_id) > 1) x"""))
    print("identities with >1 distinct resolved line:", q(c, """select count(*) from (
        select o.line_identity_key from shipment_evidence_observation o join dim_product p on p.id=o.product_id
        group by 1 having count(distinct p.product_line) > 1) x"""))
    print("null-product obs: identity has resolved obs / none:", q(c, """select
        count(*) filter (where exists (select 1 from shipment_evidence_observation r where r.line_identity_key=o.line_identity_key and r.product_id is not null)),
        count(*) filter (where not exists (select 1 from shipment_evidence_observation r where r.line_identity_key=o.line_identity_key and r.product_id is not null))
        from shipment_evidence_observation o where o.product_id is null"""))
    # line -> identities
    print("line: obs per line distinct identities >1:", q(c, """select count(*) from (select evidence_line_id from shipment_evidence_observation
        where evidence_line_id is not null group by 1 having count(distinct line_identity_key) > 1) x"""))
    print("null-product lines: with obs / without obs:", q(c, """select
        count(*) filter (where exists (select 1 from shipment_evidence_observation o where o.evidence_line_id=s.id)),
        count(*) filter (where not exists (select 1 from shipment_evidence_observation o where o.evidence_line_id=s.id))
        from shipment_evidence_line s where s.product_id is null"""))
    print("null-product lines whose identity resolves:", q(c, """select count(*) from shipment_evidence_line s where s.product_id is null
        and exists (select 1 from shipment_evidence_observation o join shipment_evidence_observation r on r.line_identity_key=o.line_identity_key
                    where o.evidence_line_id=s.id and r.product_id is not null)"""))
    # timing of current-id selection
    t0 = time.perf_counter()
    n = c.execute(sa.text("""select count(*) from (select distinct on (line_identity_key) id from shipment_evidence_observation
        where superseded_by_id is null order by line_identity_key, valid_from desc nulls last, id desc) x""")).scalar_one()
    print(f"current ids: {n} in {round((time.perf_counter()-t0)*1000)} ms")
    t0 = time.perf_counter()
    n = c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
    print(f"view rows under '*': {n} in {round((time.perf_counter()-t0)*1000)} ms")

    # Other protected tables: NULL-product rows and identity-like columns
    tabs = q(c, """select tablename from pg_policies where policyname='cip_pl_select' and tablename <> 'dim_product' order by 1""")
    print("protected tables (excl dim_product):", len(tabs))
    for (t,) in tabs:
        cols = [r[0] for r in q(c, "select column_name from information_schema.columns where table_schema='public' and table_name=:t", t=t)]
        pcol = "product_id" if "product_id" in cols else "canonical_product_id"
        tot, nul = q(c, f'select count(*), count(*) filter (where "{pcol}" is null) from "{t}"')[0]
        idc = [x for x in cols if x in ("line_identity_key", "item_code", "sku", "raw_sku", "source_sku", "model", "model_code",
                                         "sales_model_name", "evidence_line_id", "observation_id", "shipment_evidence_line_id")]
        if nul:
            print(f"  {t:45} {pcol:22} total={tot:8} null={nul:7} id-like cols={idc}")
    c.rollback()
eng.dispose()
