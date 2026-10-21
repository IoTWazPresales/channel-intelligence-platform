"""N-0065 round 3: read-only catalogue inspection of cip_test or cip.

Run from apps/api with its venv: python <this> cip_test|cip
READ ONLY transaction; prints current_database() first; prints no credentials.
"""

from __future__ import annotations

import sys

import sqlalchemy as sa

from app.core.config import get_settings


def url_for(db: str) -> str:
    u = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    base, _, tail = u.rpartition("/")
    q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/{db}{q}"


def main() -> None:
    target = sys.argv[1]
    assert target in ("cip_test", "cip")
    eng = sa.create_engine(url_for(target), poolclass=sa.pool.NullPool)
    with eng.connect() as c:
        c.execute(sa.text("SET TRANSACTION READ ONLY"))
        db = c.execute(sa.text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == target
        r = c.execute(sa.text("select current_user, rolsuper, rolbypassrls from pg_roles where rolname=current_user")).one()
        print("role:", tuple(r))
        try:
            print("alembic:", c.execute(sa.text("select version_num from alembic_version")).scalars().all())
        except Exception as e:  # noqa: BLE001
            print("alembic: error", type(e).__name__)
            c.rollback()
            c.execute(sa.text("SET TRANSACTION READ ONLY"))
        print("server_version:", c.execute(sa.text("show server_version")).scalar_one())
        rows = c.execute(sa.text("""
            select p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig
            from pg_proc p where p.proname like 'cip_product_%' order by 1""")).all()
        print("functions:", [tuple(x) for x in rows])
        rls = c.execute(sa.text("""
            select count(*) filter (where relrowsecurity), count(*) filter (where relforcerowsecurity)
            from pg_class where relkind='r' and relnamespace='public'::regnamespace""")).one()
        print("tables rls/force:", tuple(rls))
        pol = c.execute(sa.text("select count(distinct tablename) from pg_policies where policyname='cip_pl_select'")).scalar_one()
        print("tables with cip_pl_select:", pol)
        kinds = c.execute(sa.text("""
            select case when qual like '%cip_product_id_visible%' then 'definer_fn_0024'
                        when qual like '%dim_product%' then 'inline_0025'
                        else 'line_fn' end, count(*)
            from pg_policies where policyname = 'cip_pl_select' group by 1 order by 1""")).all()
        print("select policy kinds:", [tuple(x) for x in kinds])
        ekinds = c.execute(sa.text("""
            select policyname, case when coalesce(qual, with_check) like '%cip_product_id_editable%' then 'definer_fn_0024'
                        when coalesce(qual, with_check) like '%dim_product%' then 'inline_0025'
                        else 'line_fn' end, count(*)
            from pg_policies where policyname in ('cip_pl_insert','cip_pl_update','cip_pl_delete')
            group by 1, 2 order by 1, 2""")).all()
        print("edit policy kinds:", [tuple(x) for x in ekinds])
        sample = c.execute(sa.text(
            "select qual from pg_policies where policyname='cip_pl_select' and tablename='fact_sales_sellout'")).scalar()
        print("fact_sales_sellout select qual:", sample)
        owners = c.execute(sa.text("""
            select pg_get_userbyid(relowner), count(*) from pg_class
            where relkind in ('r','v','m') and relnamespace='public'::regnamespace group by 1 order by 1""")).all()
        print("owners (r/v/m):", [tuple(x) for x in owners])
        # Views and matviews that depend on an RLS table.
        dep = c.execute(sa.text("""
            with v as (
              select c.oid, c.relname, c.relkind, pg_get_userbyid(c.relowner) owner, c.reloptions
              from pg_class c where c.relkind in ('v','m') and c.relnamespace='public'::regnamespace)
            select v.relname, v.relkind, v.owner, v.reloptions,
                   array_agg(distinct t.relname order by t.relname) filter (where t.relrowsecurity) rls_tables
            from v
            join pg_rewrite rw on rw.ev_class = v.oid
            join pg_depend d on d.objid = rw.oid and d.classid='pg_rewrite'::regclass and d.refclassid='pg_class'::regclass
            join pg_class t on t.oid = d.refobjid and t.oid <> v.oid
            group by 1,2,3,4 order by 1""")).all()
        print("views/matviews and RLS tables they read:")
        for x in dep:
            print("  ", tuple(x))
        cols = c.execute(sa.text("""
            select count(distinct c.table_name) from information_schema.columns c
            join information_schema.tables t on t.table_schema=c.table_schema and t.table_name=c.table_name
            where c.table_schema='public' and t.table_type='BASE TABLE'
              and c.column_name in ('product_id','canonical_product_id')
              and c.data_type in ('integer','bigint','smallint') and c.table_name <> 'dim_product'""")).scalar_one()
        print("product-keyed base tables:", cols)
        print("dim_product rows (as this role, setting unset):", c.execute(sa.text("select count(*) from dim_product")).scalar_one())
        print("lines:", c.execute(sa.text("select count(distinct product_line), count(*) filter (where product_line is null) from dim_product")).one())
        c.rollback()
    eng.dispose()


if __name__ == "__main__":
    main()
