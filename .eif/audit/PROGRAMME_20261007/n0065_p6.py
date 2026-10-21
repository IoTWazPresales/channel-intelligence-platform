"""N-0065 probe 6: views/matviews in public -- owner, security_invoker, and whether a
single-line user sees other lines through them. Read-only."""
from n0065_dbh import engine, ro, sa

e = engine()
with e.connect() as c:
    ro(c)
    rows = c.execute(sa.text(
        """select c.relname, c.relkind, pg_get_userbyid(c.relowner) owner, r.rolsuper, r.rolbypassrls,
                  coalesce(c.reloptions::text, '') opts
           from pg_class c join pg_namespace n on n.oid = c.relnamespace
           join pg_roles r on r.oid = c.relowner
           where n.nspname = 'public' and c.relkind in ('v','m') order by 1""")).fetchall()
    for r in rows:
        print(r)
    c.execute(sa.text("select set_config('cip.product_lines', 'NB', true)"))
    print("-- NB user: product lines visible through shipment_evidence_current vs base table")
    print("view:", c.execute(sa.text(
        "select count(*), count(*) filter (where p.product_line is distinct from 'NB') from shipment_evidence_current v"
        " left join (select id, product_line from dim_product) p on p.id = v.product_id")).fetchall())
    print("view rows whose product is invisible to NB user (no dim_product row visible):", c.execute(sa.text(
        "select count(*) from shipment_evidence_current v where v.product_id is not null"
        " and not exists (select 1 from dim_product p where p.id = v.product_id)")).scalar())
    print("base shipment_evidence_line rows visible:", c.execute(sa.text(
        "select count(*) from shipment_evidence_line")).scalar())
