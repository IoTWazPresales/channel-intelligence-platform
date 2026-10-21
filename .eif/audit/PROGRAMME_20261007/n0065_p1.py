"""N-0065 perf probe 1: role, functions, RLS tables, GUC reset behaviour. Read-only."""
from n0065_dbh import engine, ro, sa

e = engine()
with e.connect() as c:
    ro(c)
    print(c.execute(sa.text("select current_user, version()")).fetchall())
    print(c.execute(sa.text(
        "select rolname, rolsuper, rolbypassrls from pg_roles where rolname=current_user")).fetchall())
    print("-- functions")
    for r in c.execute(sa.text(
            "select proname, provolatile, proleakproof, prosecdef, proconfig, pg_get_userbyid(proowner),"
            " (select lanname from pg_language l where l.oid=prolang) from pg_proc where proname like 'cip_product%'")):
        print(r)
    print("-- rls tables")
    rows = c.execute(sa.text(
        """select c.relname, pg_get_userbyid(c.relowner), c.relrowsecurity, c.relforcerowsecurity,
                  c.reltuples::bigint, pg_size_pretty(pg_total_relation_size(c.oid))
           from pg_class c join pg_namespace n on n.oid=c.relnamespace
           where n.nspname='public' and c.relkind='r' and c.relrowsecurity
           order by c.reltuples desc""")).fetchall()
    for r in rows:
        print(r)
    print("rls table count:", len(rows))
    print("-- policies sample")
    for r in c.execute(sa.text(
            "select tablename, policyname, cmd, qual from pg_policies where tablename in"
            " ('dim_product','fact_customer_sellthrough') order by 1,2")):
        print(r)
    print("-- dim_product")
    print(c.execute(sa.text(
        "select count(*), count(distinct product_line), count(*) filter (where product_line is null)"
        " from dim_product")).fetchall())
    for r in c.execute(sa.text(
            "select product_line, count(*) from dim_product group by 1 order by 2 desc limit 15")):
        print(r)
    for r in c.execute(sa.text("select indexdef from pg_indexes where tablename='dim_product'")):
        print(r)
    c.execute(sa.text("select set_config('cip.product_lines','X',true)"))
    pid = c.execute(sa.text("select pg_backend_pid()")).scalar()
    c.rollback()
    c.execute(sa.text("SET TRANSACTION READ ONLY"))
    print("-- GUC after local set + txn end, same backend",
          c.execute(sa.text("select pg_backend_pid()")).scalar() == pid,
          repr(c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()))
